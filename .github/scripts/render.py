#!/usr/bin/env python3
"""Render the animated profile SVGs in assets/ (a dark and a light copy of each).

    python .github/scripts/render.py static     # hero, work tiles, tool wall; rerun after edits
    python .github/scripts/render.py activity   # needs GITHUB_TOKEN; the workflow runs it daily

IBM Plex (SIL Open Font License) is fetched from google/fonts and embedded as a
subset, so the images look the same on every OS. Tool icons come from
skillicons.dev and Simple Icons (CC0). Needs: pip install fonttools brotli
"""

import base64
import datetime as dt
import functools
import html
import io
import json
import math
import os
import random
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
LOGIN = "ips610"

HERO_NAME = "Ishpuneet Singh"
HERO_ROLE = "Cybersecurity and machine learning researcher"
# Each line is exactly 15 characters, so with its newline it fills one 16-byte
# hexdump row and the ASCII column ends every row with "." (0x0a).
HERO_LINES = ["binary analysis", "user biometrics", "medical imaging", "network defense"]

# Rows of the tool wall. Plain ids are skillicons.dev; "si:" ids are Simple Icons.
TOOLS = [
    ("Languages", ["py", "c", "cpp", "java", "ts", "js", "dart", "php", "r", "matlab",
                   "solidity", "bash", "html", "css"]),
    ("ML and data", ["pytorch", "tensorflow", "sklearn", "opencv", "si:huggingface", "si:jupyter",
                     "si:pandas", "si:numpy", "si:kaggle"]),
    ("Web and apps", ["react", "nextjs", "nodejs", "tailwind", "vite", "threejs", "flutter",
                      "firebase", "flask", "fastapi", "selenium", "supabase"]),
    ("Data and infra", ["mysql", "redis", "docker", "linux", "nginx", "si:apache", "gcp", "vercel",
                        "cloudflare", "git", "githubactions"]),
    ("Tools", ["latex", "arduino", "si:autocad", "androidstudio", "vscode"]),
]
SIMPLE_ICONS = "https://cdn.jsdelivr.net/npm/simple-icons@16.32.0"

# GitHub Primer colours, so the images sit naturally on either theme.
THEMES = {
    "dark": dict(ink="#f0f6fc", muted="#9198a1", faint="#3d444d", canvas="#0d1117", panel="#151b23",
                 border="#3d444d", byte="#79c0ff", space="#656c76", accent="#4493f8", red="#f85149",
                 green="#3fb950", purple="#ab7df8", pink="#db61a2", amber="#d29922", tile="#242938"),
    "light": dict(ink="#1f2328", muted="#59636e", faint="#d1d9e0", canvas="#ffffff", panel="#f6f8fa",
                  border="#d1d9e0", byte="#0969da", space="#9198a1", accent="#0969da", red="#d1242f",
                  green="#1a7f37", purple="#8250df", pink="#bf3989", amber="#9a6700", tile="#f4f2ed"),
}

FONT_CACHE = Path(os.environ.get("FONT_CACHE", Path.home() / ".cache" / "ips610-fonts"))
FONT_SOURCES = {
    "sans": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsans/IBMPlexSans%5Bwdth,wght%5D.ttf",
    "mono": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
}
SANS = 'Sans,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif'
MONO = 'Mono,ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace'


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ips610-profile-render"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


# --------------------------------------------------------------------- fonts

@functools.lru_cache(maxsize=None)
def _font_bytes(source, weight):
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    path = FONT_CACHE / f"{source}.ttf"
    if not path.exists():
        path.write_bytes(fetch(FONT_SOURCES[source]))
    font = TTFont(path, recalcTimestamp=False)
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": weight, "wdth": 100})
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def _face(source, weight, text):
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(_font_bytes(source, weight)), recalcTimestamp=False)
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["kern", "liga"]
    options.name_IDs = [0, 1, 2, 13, 14]  # keep copyright, family and licence names
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    family = "Sans" if source == "sans" else "Mono"
    return (f'@font-face{{font-family:"{family}";font-weight:{weight};'
            f'src:url(data:font/woff2;base64,{data}) format("woff2")}}')


def fonts(sans600="", sans400="", mono=""):
    rules = []
    if sans600:
        rules.append(_face("sans", 600, sans600))
    if sans400:
        rules.append(_face("sans", 400, sans400))
    if mono:
        rules.append(_face("mono", 400, mono))
    return "\n".join(rules)


def esc(s):
    return html.escape(str(s), quote=True)


def svg(width, height, title, style, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t">
<title id="t">{esc(title)}</title>
<style>
{style}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.motion{{display:none}}}}
</style>
{body}
</svg>
"""


# ---------------------------------------------------------------------- hero

def render_hero(theme):
    c = THEMES[theme]
    data = "".join(line + "\n" for line in HERO_LINES).encode()
    assert all(len(line) == 15 for line in HERO_LINES), "each hero line must be 15 chars"

    adv = 9  # 15px Plex Mono advances 0.6em
    x_hex, x_bar = 90, 540
    x_ascii = x_bar + adv
    y0, lh = 152, 26

    def hex_x(i):
        return x_hex + i * 3 * adv + (adv if i >= 8 else 0)

    parts, mono, cursor = [], "0123456789abcdef|.", []
    for row in range(len(data) // 16):
        y = y0 + row * lh
        parts.append(f'<text class="m off" x="2" y="{y}">{row * 16:08x}</text>')
        parts.append(f'<text class="m off" x="{x_bar}" y="{y}">|</text>')
        parts.append(f'<text class="m off" x="{x_ascii + 16 * adv}" y="{y}">|</text>')
        for col in range(16):
            i = row * 16 + col
            b = data[i]
            kind = "nl" if b == 0x0A else "sp" if b == 0x20 else "b"
            ch = "." if b == 0x0A else chr(b)
            mono += ch
            delay = f"{0.35 + i * 0.028:.3f}s"
            parts.append(f'<text class="m {kind} hx" x="{hex_x(col)}" y="{y}" '
                         f'style="animation-delay:{delay}">{b:02x}</text>')
            if ch != " ":
                parts.append(f'<text class="m {kind} dec" x="{x_ascii + col * adv}" y="{y}" '
                             f'style="animation-delay:{delay}">{esc(ch)}</text>')
            cursor.append((hex_x(col) - 3, x_ascii + col * adv - 1, y - 15))
    end_y = y0 + (len(data) // 16) * lh
    parts.append(f'<text class="m off" x="2" y="{end_y}">{len(data):08x}</text>')
    parts.append(f'<rect class="caret" x="84" y="{end_y - 13}" width="9" height="16" rx="1"/>')

    # A hex-editor cursor that keeps walking the bytes, lighting the matching character.
    begin, dur = "2.6s", f"{len(cursor) * 0.18:.2f}s"

    def walk(attr, values):
        return (f'<animate attributeName="{attr}" values="{";".join(map(str, values))}" dur="{dur}" '
                f'begin="{begin}" repeatCount="indefinite" calcMode="discrete"/>')

    ys = [y for _, _, y in cursor]
    hx0, ax0, cy0 = cursor[0]
    parts.insert(0, f"""<g class="motion" opacity="0"><set attributeName="opacity" to="1" begin="{begin}"/>
<rect class="cur" x="{hx0}" y="{cy0}" width="24" height="21" rx="3">{walk("x", [x for x, _, _ in cursor])}{walk("y", ys)}</rect>
<rect class="cur" x="{ax0}" y="{cy0}" width="11" height="21" rx="2">{walk("x", [a for _, a, _ in cursor])}{walk("y", ys)}</rect>
</g>""")

    style = fonts(HERO_NAME, HERO_ROLE, mono) + f"""
.name{{font:600 50px {SANS};fill:{c["ink"]};letter-spacing:-.02em}}
.role{{font:400 19px {SANS};fill:{c["muted"]}}}
.m{{font:400 15px {MONO}}}
.off{{fill:{c["space"]}}}.b{{fill:{c["byte"]}}}.sp{{fill:{c["space"]}}}.nl{{fill:{c["amber"]}}}
.cur{{fill:{c["byte"]};fill-opacity:.2}}
.caret{{fill:{c["byte"]};animation:blink 1.1s steps(1) infinite}}
.hx{{animation:hx .4s ease-out backwards}}.dec{{animation:dec .4s ease-out backwards}}
@keyframes hx{{from{{opacity:.2}}}}@keyframes dec{{from{{opacity:0}}}}@keyframes blink{{50%{{opacity:0}}}}"""
    body = (f'<text class="name" x="0" y="60">{esc(HERO_NAME)}</text>\n'
            f'<text class="role" x="1" y="98">{esc(HERO_ROLE)}</text>\n' + "\n".join(parts))
    return svg(720, end_y + 22, f"{HERO_NAME}, {HERO_ROLE}", style, body)


# --------------------------------------------------------------- work tiles
# Each stage function takes the theme colours and returns (css, body, mono text, sans text).

TILE_W, TILE_H, STAGE_H = 400, 272, 184


def tile(theme, title, lines, stage):
    c = THEMES[theme]
    css, body, mono, sans = stage(c)
    style = fonts(title, "".join(lines) + sans, mono) + f"""
.tt{{font:600 17px {SANS};fill:{c["ink"]}}}
.cap{{font:400 13.5px {SANS};fill:{c["muted"]}}}
{css}"""
    caps = "\n".join(f'<text class="cap" x="20" y="{238 + i * 19}">{esc(line)}</text>'
                     for i, line in enumerate(lines))
    frame = f"""<clipPath id="stage"><rect x="1" y="1" width="{TILE_W - 2}" height="{STAGE_H}"/></clipPath>
<rect x=".5" y=".5" width="{TILE_W - 1}" height="{TILE_H - 1}" rx="6" fill="{c["panel"]}" stroke="{c["border"]}"/>
<path d="M1 {STAGE_H + 1}V7a6 6 0 0 1 6-6h{TILE_W - 14}a6 6 0 0 1 6 6v{STAGE_H - 6}z" fill="{c["canvas"]}"/>
<g clip-path="url(#stage)" class="s">
{body}
</g>
<path d="M1 {STAGE_H + 1.5}H{TILE_W - 1}" stroke="{c["border"]}"/>
<text class="tt" x="20" y="216">{esc(title)}</text>
{caps}"""
    return svg(TILE_W, TILE_H, f"{title}. {' '.join(lines)}", style, frame)


def shadow_stage(c):
    """Bytes stream up through a scanning lens; bytes the model attends to turn red inside it."""
    rnd = random.Random(0x5AD0)
    rows, lh, per = 22, 22, 8
    data = [0x4D, 0x5A] + [0 if rnd.random() < 0.3 else rnd.randrange(256) for _ in range(rows * per - 2)]
    hot = {i for i, b in enumerate(data) if b and rnd.random() < 0.12}
    adv = 7.8  # 13px mono

    def layer(bright):
        out = []
        for copy in range(2):  # a second copy underneath makes the loop seamless
            for r in range(rows):
                y = (copy * rows + r) * lh + 16
                cls = "o" if bright else "d"
                out.append(f'<text class="{cls}" x="26" y="{y}">{r * per:08x}</text>')
                for j in range(per):
                    i = r * per + j
                    b = data[i]
                    if bright:
                        cls = "hot" if i in hot else "z" if b == 0 else "v"
                    out.append(f'<text class="{cls}" x="{104 + j * 3 * adv:.1f}" y="{y}">{b:02x}</text>')
                    ch = chr(b) if 0x20 < b < 0x7F else "."
                    out.append(f'<text class="{cls if bright else "d"}" x="{304 + j * adv:.1f}" y="{y}">{esc(ch)}</text>')
        return "\n".join(out)

    printable = "".join(chr(b) for b in data if 0x20 < b < 0x7F)
    body = f"""<defs>
<linearGradient id="fg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".3" stop-color="#fff"/><stop offset=".7" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<mask id="fade"><rect width="{TILE_W}" height="{STAGE_H}" fill="url(#fg)"/></mask>
<clipPath id="lens"><rect x="0" y="81" width="{TILE_W}" height="22"/></clipPath>
</defs>
<g mask="url(#fade)"><g class="up">{layer(False)}</g></g>
<rect x="0" y="81" width="{TILE_W}" height="22" class="band"/>
<path d="M0 81.5H{TILE_W}M0 102.5H{TILE_W}" class="edge"/>
<g clip-path="url(#lens)"><g class="up">{layer(True)}</g></g>"""
    css = f""".s text{{font:400 13px {MONO}}}
.d{{fill:{c["space"]};fill-opacity:.55}}.o{{fill:{c["muted"]}}}.z{{fill:{c["space"]}}}.v{{fill:{c["byte"]}}}.hot{{fill:{c["red"]}}}
.band{{fill:{c["accent"]};fill-opacity:.1}}.edge{{stroke:{c["accent"]};stroke-opacity:.6}}
.up{{animation:up {rows * 0.8:.1f}s linear infinite}}@keyframes up{{to{{transform:translateY(-{rows * lh}px)}}}}"""
    return css, body, "0123456789abcdef." + printable, ""


def beacon_stage(c):
    """Keyboard, mouse and network signals scroll past, like a live capture."""
    rnd = random.Random(79)
    x0, period = 72, 308
    lanes = [("keys", 50, c["byte"]), ("mouse", 98, c["purple"]), ("net", 146, c["green"])]

    keys, x = [], 4.0
    while x < period - 18:
        w = rnd.uniform(5, 15)
        keys.append((x, w))
        x += w + rnd.uniform(6, 26)
    packets = []
    for _ in range(8):
        cx = rnd.uniform(0, period - 26)
        for j in range(rnd.randint(2, 6)):
            packets.append((cx + j * rnd.uniform(3, 5), rnd.uniform(5, 26)))

    def wave(x):
        t = 2 * math.pi * x / period
        return 13 * (0.55 * math.sin(2 * t) + 0.3 * math.sin(5 * t + 1.3) + 0.15 * math.sin(9 * t + 0.4))

    mouse = "M" + " L".join(f"{x0 + x},{98 + wave(x):.1f}" for x in range(0, 2 * period + 1, 3))
    signals = []
    for copy in (0, period):
        signals += [f'<rect x="{x0 + copy + kx:.1f}" y="43" width="{kw:.1f}" height="14" rx="2" fill="{c["byte"]}"/>'
                    for kx, kw in keys]
        signals += [f'<path d="M{x0 + copy + px:.1f} 158V{158 - ph:.1f}" stroke="{c["green"]}" stroke-width="2"/>'
                    for px, ph in packets]
    signals.append(f'<path d="{mouse}" fill="none" stroke="{c["purple"]}" stroke-width="1.8" stroke-linejoin="round"/>')

    labels = "\n".join(f'<text class="lb" x="20" y="{y + 4}">{name}</text>' for name, y, _ in lanes)
    dots = "\n".join(f'<circle class="dot" cx="382" cy="{y if name != "net" else 150}" r="3.5" fill="{col}" '
                     f'style="animation-delay:{i * 0.3}s"/>' for i, (name, y, col) in enumerate(lanes))
    body = f"""<defs>
<linearGradient id="fg"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".18" stop-color="#fff"/></linearGradient>
<mask id="fade"><rect x="{x0}" width="{382 - x0}" height="{STAGE_H}" fill="url(#fg)"/></mask>
</defs>
<path d="M{x0} 158.5H382" stroke="{c["faint"]}"/>
<g mask="url(#fade)"><g class="left">{"".join(signals)}</g></g>
<path d="M382.5 20V168" stroke="{c["faint"]}" stroke-dasharray="2 3"/>
{dots}
{labels}"""
    css = f""".s text{{font:400 11.5px {MONO}}}.lb{{fill:{c["muted"]}}}
.left{{animation:left 8s linear infinite}}@keyframes left{{to{{transform:translateX(-{period}px)}}}}
.dot{{animation:pulse 1.4s ease-in-out infinite}}@keyframes pulse{{50%{{opacity:.25}}}}"""
    return css, body, "keysmouenet", ""


def medical_stage(c):
    """A retina feeds concepts, which feed the diagnosis. A clinician's cursor rejects
    one concept and the diagnosis updates, which is the point of a concept bottleneck."""
    concepts = ["vessels", "optic disc", "exudates", "haemorrhages"]
    ys = [34, 72, 110, 148]
    cx, cy, r = 70, 92, 48
    fundus = f"""<radialGradient id="fundus" cx=".42" cy=".42" r=".65"><stop offset="0" stop-color="#f7a35c"/><stop offset=".65" stop-color="#d9591f"/><stop offset="1" stop-color="#8f2a0e"/></radialGradient>
<clipPath id="eye"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>"""
    vessels = ["M88 86C72 72 56 62 26 60", "M88 86C72 98 58 112 30 124", "M88 86C96 66 92 54 82 42",
               "M88 86C98 102 96 118 86 136", "M88 86C74 86 58 90 22 92", "M88 86C104 80 112 72 118 70"]
    eye = f"""<g clip-path="url(#eye)"><circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#fundus)"/>
{"".join(f'<path d="{d}" fill="none" stroke="#6e1a07" stroke-width="{2.2 - i * 0.2:.1f}" stroke-linecap="round"/>' for i, d in enumerate(vessels))}
<circle cx="88" cy="86" r="10" fill="#fde2a8"/>
<circle cx="52" cy="108" r="3.5" fill="#6e1205"/><circle cx="60" cy="74" r="1.8" fill="#ffe08a"/><circle cx="66" cy="70" r="1.5" fill="#ffe08a"/><circle cx="46" cy="84" r="1.6" fill="#ffe08a"/></g>
<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{c["border"]}"/>"""

    edges = []
    for y in ys:
        for d in (f"M118 {cy}C138 {cy} 138 {y} 158 {y}", f"M262 {y}C280 {y} 280 {cy} 298 {cy}"):
            edges.append(f'<path d="{d}" class="wire"/><path d="{d}" class="flow"/>')
    pills, keyframes = [], []
    for i, (name, y) in enumerate(zip(concepts, ys)):
        on = 12 + 7 * i
        pills.append(f'<rect class="p p{i}" x="158" y="{y - 12}" width="104" height="24" rx="12"/>'
                     f'<text class="pl pl{i}" x="210" y="{y + 4}">{name}</text>')
        if i < 3:
            keyframes.append(f"@keyframes p{i}{{0%,{on - 0.1}%{{fill-opacity:0;stroke:{c['border']}}}{on + 3}%,92%{{fill-opacity:.16;stroke:{c['accent']}}}100%{{fill-opacity:0;stroke:{c['border']}}}}}")
        else:  # the concept the clinician rejects
            keyframes.append(f"@keyframes p{i}{{0%,{on - 0.1}%{{fill-opacity:0;stroke:{c['border']}}}{on + 3}%,55%{{fill-opacity:.16;stroke:{c['accent']};stroke-dasharray:none}}57%,92%{{fill-opacity:0;stroke:{c['amber']};stroke-dasharray:4 3}}100%{{fill-opacity:0;stroke:{c['border']}}}}}")
        keyframes.append(f"@keyframes pl{i}{{0%,{on - 0.1}%{{fill:{c['muted']}}}{on + 3}%,92%{{fill:{c['ink']}}}100%{{fill:{c['muted']}}}}}")
    pills.append(f'<path class="strike" d="M172 {ys[3]}H248" stroke="{c["amber"]}" stroke-width="1.5"/>')

    pred = f"""<rect x="298" y="64" width="86" height="56" rx="8" fill="{c["panel"]}" stroke="{c["border"]}"/>
<text class="pl" x="341" y="86" style="animation:none;fill:{c["ink"]}">diagnosis</text>
<rect x="310" y="97" width="62" height="7" rx="3.5" fill="{c["faint"]}"/>
<rect class="meter" x="310" y="97" width="62" height="7" rx="3.5" fill="{c["accent"]}"/>"""
    pointer = (f'<g class="ptr"><path d="M0 0L0 15L4 11.5L7 18L9.5 17L6.5 10.5L11.5 10.5Z" '
               f'fill="{c["ink"]}" stroke="{c["canvas"]}" stroke-width="1.2" stroke-linejoin="round"/></g>')

    body = f"<defs>{fundus}</defs>\n{eye}\n{''.join(edges)}\n{''.join(pills)}\n{pred}\n{pointer}"
    css = f""".s text{{font:400 12px {SANS}}}.pl{{text-anchor:middle;fill:{c["ink"]}}}
.wire{{fill:none;stroke:{c["faint"]};stroke-width:1.2}}
.flow{{fill:none;stroke:{c["accent"]};stroke-width:1.6;stroke-dasharray:2 7;animation:flow .9s linear infinite}}
@keyframes flow{{to{{stroke-dashoffset:-9}}}}
.p{{fill:{c["accent"]};fill-opacity:.16;stroke:{c["accent"]}}}
{"".join(f".p{i}{{animation:p{i} 9s infinite}}.pl{i}{{animation:pl{i} 9s infinite}}" for i in range(4))}
{"".join(keyframes)}
.strike{{opacity:0;animation:strike 9s infinite}}@keyframes strike{{0%,56%{{opacity:0}}57%,92%{{opacity:1}}100%{{opacity:0}}}}
.meter{{transform-box:fill-box;transform-origin:0 50%;transform:scaleX(.85);animation:meter 9s ease-in-out infinite}}
@keyframes meter{{0%,12%{{transform:scaleX(0)}}36%,55%{{transform:scaleX(.85)}}62%,92%{{transform:scaleX(.42)}}100%{{transform:scaleX(0)}}}}
.ptr{{opacity:0;animation:ptr 9s ease-in-out infinite}}
@keyframes ptr{{0%,40%{{opacity:0;transform:translate(372px,196px)}}44%{{opacity:1;transform:translate(360px,182px)}}53%{{transform:translate(246px,152px)}}55%{{transform:translate(246px,152px) scale(.8)}}57%{{transform:translate(246px,152px) scale(1)}}66%{{opacity:1;transform:translate(258px,160px)}}72%,100%{{opacity:0;transform:translate(258px,160px)}}}}"""
    return css, body, "", "".join(concepts) + "diagnosis"


def thapar_stage(c):
    """A week fills in slot by slot; one exam lands on a clash, flashes, and moves."""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    colours = [c["accent"], c["purple"], c["green"], c["amber"], c["pink"]]
    blocks = [(0, 0, "UCS301"), (2, 1, "UML501"), (4, 0, "UCS414"), (1, 2, "UCS415"), (3, 3, "UCS411"),
              (0, 2, "UCS413"), (2, 3, "UMA021"), (4, 1, "UES013"), (1, 0, "UCS303"), (3, 1, "UHU005"),
              (0, 3, "UCS520"), (2, 0, "UCS701"), (4, 3, "UEC001")]
    clash_from, clash_to, clash_code = (2, 1), (3, 2), "UCS648"

    def cell(col, row):
        return 22 + col * 72, 36 + row * 36

    parts = [f'<text class="day" x="{cell(i, 0)[0] + 32}" y="24">{d}</text>' for i, d in enumerate(days)]
    parts += [f'<rect x="{cell(col, row)[0]}" y="{cell(col, row)[1]}" width="64" height="28" rx="5" class="slot"/>'
              for col in range(5) for row in range(4)]
    css = []
    for i, (col, row, code) in enumerate(blocks):
        x, y = cell(col, row)
        colour = colours[i % len(colours)]
        t = 5 + i * 3.2
        parts.append(f'<g class="b{i}"><rect x="{x}" y="{y}" width="64" height="28" rx="5" fill="{colour}" '
                     f'fill-opacity=".16" stroke="{colour}"/><text x="{x + 32}" y="{y + 18}" fill="{colour}">{code}</text></g>')
        css.append(f".b{i}{{transform-box:fill-box;transform-origin:center;animation:b{i} 10s infinite}}"
                   f"@keyframes b{i}{{0%,{t:.1f}%{{opacity:0;transform:scale(.6)}}{t + 3:.1f}%,90%{{opacity:1;transform:scale(1)}}95%,100%{{opacity:0;transform:scale(1)}}}}")
    fx, fy = cell(*clash_from)
    tx, ty = cell(*clash_to)
    colour = c["accent"]
    parts.append(f'<g class="cf"><rect class="cfr" x="{tx}" y="{ty}" width="64" height="28" rx="5" fill-opacity=".16"/>'
                 f'<text class="cft" x="{tx + 32}" y="{ty + 18}">{clash_code}</text></g>')
    dx, dy = fx - tx, fy - ty
    css.append(f""".cf{{animation:cf 10s infinite}}
@keyframes cf{{0%,47.9%{{opacity:0;transform:translate({dx}px,{dy}px)}}50%,56%{{opacity:1;transform:translate({dx}px,{dy}px)}}52%,54%{{transform:translate({dx + 2}px,{dy}px)}}53%{{transform:translate({dx - 2}px,{dy}px)}}63%,90%{{opacity:1;transform:translate(0,0)}}95%,100%{{opacity:0;transform:translate(0,0)}}}}
.cfr{{fill:{colour};stroke:{colour};animation:cfr 10s infinite}}@keyframes cfr{{0%,57%{{fill:{c["red"]};stroke:{c["red"]}}}63%,100%{{fill:{colour};stroke:{colour}}}}}
.cft{{fill:{colour};animation:cft 10s infinite}}@keyframes cft{{0%,57%{{fill:{c["red"]}}}63%,100%{{fill:{colour}}}}}""")
    style = f""".s text{{font:400 11px {MONO};text-anchor:middle}}.day{{fill:{c["muted"]}}}
.slot{{fill:none;stroke:{c["faint"]};stroke-dasharray:3 3}}
{"".join(css)}"""
    codes = "".join(code for _, _, code in blocks) + clash_code + "".join(days)
    return style, "\n".join(parts), codes, ""


WORK = [
    ("shadow", "SHADOW", ["Spotting malware from raw executable bytes",
                          "Foundation model, with Dr. Maninder Singh"], shadow_stage),
    ("beacon", "BEACON", ["Recognizing players by how they play",
                          "442 GB open dataset on Hugging Face"], beacon_stage),
    ("medical", "Interpretable medical AI", ["Diagnoses that clinicians can check and correct",
                                             "With Prof. Tim Miller, University of Queensland"], medical_stage),
    ("thapar", "Built for Thapar", ["Exam scheduling, timetables and course feedback",
                                    "Used across the university by 10,000+ students"], thapar_stage),
]


# ----------------------------------------------------------------- tool wall

ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def _luminance(hex_colour):
    rgb = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@functools.lru_cache(maxsize=None)
def _simple_icons_meta():
    data = json.loads(fetch(f"{SIMPLE_ICONS}/data/simple-icons.json"))
    icons = data if isinstance(data, list) else data["icons"]
    return {i.get("slug") or i["title"].lower(): i["hex"] for i in icons}


def _simple_icon(slug, theme):
    """A Simple Icons glyph on the same rounded tile skillicons uses."""
    c = THEMES[theme]
    path = re.search(r'<path d="([^"]+)"', fetch(f"{SIMPLE_ICONS}/icons/{slug}.svg").decode()).group(1)
    colour = "#" + _simple_icons_meta()[slug]
    if _contrast(colour, c["tile"]) < 1.8:  # e.g. NumPy navy on the dark tile
        colour = "#ffffff" if theme == "dark" else "#242938"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">'
            f'<rect width="256" height="256" rx="60" fill="{c["tile"]}"/>'
            f'<path transform="translate(53 53) scale(6.25)" d="{path}" fill="{colour}"/></svg>')


def _skill_icons(ids, theme):
    root = ET.fromstring(fetch(f"https://skillicons.dev/icons?i={','.join(ids)}&theme={theme}&perline=50"))
    icons = [ET.tostring(g[0], encoding="unicode") for g in root]
    assert len(icons) == len(ids), f"skillicons returned {len(icons)} of {len(ids)} icons"
    return dict(zip(ids, icons))


def render_tools(theme):
    c = THEMES[theme]
    plain = [i for _, row in TOOLS for i in row if not i.startswith("si:")]
    icons = _skill_icons(plain, theme)
    size, pitch, x0, row_h = 37, 43, 118, 50
    parts, n = [], 0
    for r, (label, row) in enumerate(TOOLS):
        y = 8 + r * row_h
        parts.append(f'<text class="lb" x="0" y="{y + size / 2 + 5:.1f}">{esc(label)}</text>')
        for col, tool in enumerate(row):
            icon = _simple_icon(tool[3:], theme) if tool.startswith("si:") else icons[tool]
            parts.append(
                f'<g class="pop" style="animation-delay:{0.2 + n * 0.025:.3f}s">'
                f'<g class="wave" style="animation-delay:{1.8 + col * 0.08 + r * 0.3:.2f}s">'
                f'<g transform="translate({x0 + col * pitch} {y}) scale({size / 256:.5f})">{icon}</g></g></g>')
            n += 1
    height = 8 + len(TOOLS) * row_h
    labels = "".join(label for label, _ in TOOLS)
    style = fonts(sans400=labels) + f"""
.lb{{font:400 13px {SANS};fill:{c["muted"]}}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.2,.8,.3,1.25) backwards}}
@keyframes pop{{from{{opacity:0;transform:scale(.6)}}}}
.wave{{animation:wave 8s ease-in-out infinite}}
@keyframes wave{{0%,10%,100%{{transform:translateY(0)}}5%{{transform:translateY(-5px)}}}}"""
    names = ", ".join(t[3:] if t.startswith("si:") else t for _, row in TOOLS for t in row)
    return svg(720, height, f"Tools: {names}", style, "\n".join(parts))


# ------------------------------------------------------------------ activity

CALENDAR = "contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}"


def graphql(query, variables):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch_contributions():
    """The past-year calendar, plus every day since the account was created."""
    user = graphql("query($login:String!){user(login:$login){createdAt contributionsCollection{%s}}}"
                   % CALENDAR, {"login": LOGIN})
    past_year = user["contributionsCollection"]["contributionCalendar"]
    days = {}

    def add(calendar):
        for week in calendar["weeks"]:
            for d in week["contributionDays"]:
                days[d["date"]] = max(days.get(d["date"], 0), d["contributionCount"])

    # The API serves at most a year per request, so walk forward a year at a time.
    start = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        add(graphql(
            "query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){"
            "contributionsCollection(from:$from,to:$to){%s}}}" % CALENDAR,
            {"login": LOGIN, "from": start.isoformat(), "to": end.isoformat()},
        )["contributionsCollection"]["contributionCalendar"])
        start = end
    add(past_year)  # can run a day ahead of UTC, in the viewer's time zone
    return past_year, days


def summarise(past_year, days):
    counts = [days[d] for d in sorted(days)]

    longest = run = 0
    for n in counts:
        run = run + 1 if n else 0
        longest = max(longest, run)

    current = 0
    tail = counts[:-1] if counts and counts[-1] == 0 else counts  # today may not be over yet
    for n in reversed(tail):
        if not n:
            break
        current += 1

    weeks = [(w["contributionDays"][0]["date"], sum(d["contributionCount"] for d in w["contributionDays"]))
             for w in past_year["weeks"]]
    return past_year["totalContributions"], current, longest, weeks


def plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def render_activity(theme, stats):
    c = THEMES[theme]
    total, current, longest, weeks = stats
    width, height = 720, 158
    figures = [
        (f"{total:,}", "contributions in the past year"),
        (plural(current, "day"), "current streak"),
        (plural(longest, "day"), "longest streak"),
    ]

    parts, sans_600, sans_400 = [], "", ""
    for i, (value, label) in enumerate(figures):
        x = i * 240
        parts.append(f'<text class="v" x="{x}" y="32">{esc(value)}</text>')
        dx = 12 if i == 1 else 0
        if dx and current:
            parts.append(f'<circle class="live" cx="{x + 4}" cy="49.5" r="4" fill="{c["green"]}"/>')
        parts.append(f'<text class="l" x="{x + 1 + (dx if current else 0)}" y="54">{esc(label)}</text>')
        sans_600 += value
        sans_400 += label

    top, span = 82, 44
    pitch = width / len(weeks)
    peak = max((n for _, n in weeks), default=0) or 1
    last_month = None
    for i, (start, n) in enumerate(weeks):
        x = i * pitch + 1.5
        h = max(2.0, span * (n / peak) ** 0.5) if n else 2.0
        cls = "bar" if n else "nil"
        if i == len(weeks) - 1 and n:
            cls += " now"
        parts.append(f'<rect class="{cls}" style="animation-delay:{0.2 + i * 0.012:.3f}s" x="{x:.1f}" '
                     f'y="{top + span - h:.1f}" width="{pitch - 3:.1f}" height="{h:.1f}" rx="1.5"><title>'
                     f'{plural(n, "contribution")} in the week of {start}</title></rect>')
        month = dt.date.fromisoformat(start).strftime("%b")
        if month != last_month and i < len(weeks) - 2:
            if last_month is not None:  # skip the partial month at the left edge
                parts.append(f'<text class="mo" x="{x:.1f}" y="{top + span + 22}">{month}</text>')
                sans_400 += month
            last_month = month

    style = fonts(sans_600, sans_400) + f"""
.v{{font:600 26px {SANS};fill:{c["ink"]};letter-spacing:-.01em}}
.l{{font:400 14px {SANS};fill:{c["muted"]}}}
.mo{{font:400 12px {SANS};fill:{c["muted"]}}}
.bar{{fill:{c["accent"]}}}.nil{{fill:{c["faint"]}}}
.bar,.nil{{transform-box:fill-box;transform-origin:50% 100%;animation:grow .7s cubic-bezier(.2,.7,.2,1) backwards}}
.now{{animation:grow .7s cubic-bezier(.2,.7,.2,1) backwards,glow 2.4s 1.5s ease-in-out infinite}}
@keyframes grow{{from{{transform:scaleY(0)}}}}@keyframes glow{{50%{{opacity:.45}}}}
.live{{animation:glow 1.6s ease-in-out infinite}}"""
    title = (f"{total:,} contributions in the past year; current streak {plural(current, 'day')}; "
             f"longest streak {plural(longest, 'day')}")
    return svg(width, height, title, style, "\n".join(parts))


# ---------------------------------------------------------------------- main

def main():
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "static":
        for theme in THEMES:
            (ASSETS / f"hero-{theme}.svg").write_text(render_hero(theme))
            for key, title, lines, stage in WORK:
                (ASSETS / f"work-{key}-{theme}.svg").write_text(tile(theme, title, lines, stage))
            (ASSETS / f"tools-{theme}.svg").write_text(render_tools(theme))
    elif what == "activity":
        stats = summarise(*fetch_contributions())
        for theme in THEMES:
            (ASSETS / f"activity-{theme}.svg").write_text(render_activity(theme, stats))
        print(f"{stats[0]} contributions, current streak {stats[1]}, longest {stats[2]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
