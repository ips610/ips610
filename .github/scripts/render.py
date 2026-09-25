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

# Rows of the tool wall: (icon id, name shown on hover). Plain ids are
# skillicons.dev; "si:" ids are Simple Icons.
TOOLS = [
    ("Languages", [("py", "Python"), ("c", "C"), ("cpp", "C++"), ("java", "Java"), ("ts", "TypeScript"),
                   ("js", "JavaScript"), ("dart", "Dart"), ("php", "PHP"), ("r", "R"), ("matlab", "MATLAB"),
                   ("solidity", "Solidity"), ("bash", "Bash"), ("html", "HTML"), ("css", "CSS")]),
    ("ML and data", [("pytorch", "PyTorch"), ("tensorflow", "TensorFlow"), ("sklearn", "scikit-learn"),
                     ("opencv", "OpenCV"), ("si:huggingface", "Hugging Face"), ("si:jupyter", "Jupyter"),
                     ("si:pandas", "pandas"), ("si:numpy", "NumPy"), ("si:kaggle", "Kaggle")]),
    ("Web and apps", [("react", "React"), ("nextjs", "Next.js"), ("nodejs", "Node.js"),
                      ("tailwind", "Tailwind CSS"), ("vite", "Vite"), ("threejs", "Three.js"),
                      ("flutter", "Flutter"), ("firebase", "Firebase"), ("flask", "Flask"),
                      ("fastapi", "FastAPI"), ("selenium", "Selenium"), ("supabase", "Supabase")]),
    ("Data and infra", [("mysql", "MySQL"), ("redis", "Redis"), ("docker", "Docker"), ("linux", "Linux"),
                        ("nginx", "Nginx"), ("si:apache", "Apache"), ("gcp", "Google Cloud"),
                        ("vercel", "Vercel"), ("cloudflare", "Cloudflare"), ("git", "Git"),
                        ("githubactions", "GitHub Actions")]),
    ("Tools", [("latex", "LaTeX"), ("arduino", "Arduino"), ("si:autocad", "AutoCAD"),
               ("androidstudio", "Android Studio"), ("vscode", "VS Code")]),
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


def fonts(sans600="", sans400="", mono="", sans500=""):
    rules = []
    if sans500:
        rules.append(_face("sans", 500, sans500))
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

    cat_x = 606
    parts.append(ascii_art([" /\\_/\\"], cat_x, 34, "cat")
                 + ascii_art(["( o.o )"], cat_x, 50, "cat open") + ascii_art(["( -.- )"], cat_x, 50, "cat shut")
                 + ascii_art([" > ^ <_/"], cat_x, 66, "cat")
                 + ascii_art([")"], cat_x + 8 * 8.4, 50, "cat ta") + ascii_art(["("], cat_x + 8 * 8.4, 50, "cat tb")
                 + f'<text class="meow" x="{cat_x - 58}" y="28">meow!</text>')
    mono += ASCII

    style = fonts(HERO_NAME, HERO_ROLE, mono) + f"""
.cat{{font:400 14px {MONO};fill:{c["ink"]};white-space:pre}}
.open{{animation:open 5s infinite}}@keyframes open{{0%,90%{{opacity:1}}90.5%,95%{{opacity:0}}95.5%,100%{{opacity:1}}}}
.shut{{opacity:0;animation:shut 5s infinite}}@keyframes shut{{0%,90%{{opacity:0}}90.5%,95%{{opacity:1}}95.5%,100%{{opacity:0}}}}
.ta{{animation:fa 1.2s steps(1) infinite}}.tb{{opacity:0;animation:fb 1.2s steps(1) infinite}}
@keyframes fa{{50%{{opacity:0}}}}@keyframes fb{{50%{{opacity:1}}}}
.meow{{font:400 12px {MONO};fill:{c["accent"]};opacity:0;animation:meow 9s 3s infinite}}
@keyframes meow{{0%{{opacity:0;transform:translateY(4px)}}4%,16%{{opacity:1;transform:translateY(0)}}22%,100%{{opacity:0;transform:translateY(-4px)}}}}
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


# ------------------------------------------------------------------ animals

ASCII = "".join(chr(i) for i in range(0x20, 0x7F))

# Two-frame animation: .fa shows on the first half of each beat, .fb on the second.
FRAMES = """.fa{{animation:fa {t} steps(1) infinite}}@keyframes fa{{50%{{opacity:0}}}}
.fb{{opacity:0;animation:fb {t} steps(1) infinite}}@keyframes fb{{50%{{opacity:1}}}}"""


def ascii_art(lines, x, y, cls, lh=16):
    return "".join(f'<text class="{cls}" x="{x}" y="{y + i * lh}" xml:space="preserve">{esc(line)}</text>'
                   for i, line in enumerate(lines))


def render_chase(theme):
    """A cat chases a mouse across the page while two birds flap the other way."""
    c = THEMES[theme]
    cat_a = ["   /\\_/\\", "~ ( o.o )", "  (\")_(\")"]
    cat_b = ["   /\\_/\\", "- ( o.o )", " (\")__(\")"]
    runners = (f'<g transform="translate(250 0)"><g class="run">'
               f'<g class="bob"><g class="fa">{ascii_art(cat_a, 0, 40, "a")}</g><g class="fb">{ascii_art(cat_b, 0, 40, "a")}</g></g>'
               f'<g class="fa">{ascii_art(["~~(__^.>"], 110, 72, "m")}</g><g class="fb">{ascii_art(["-~(__^.>"], 110, 72, "m")}</g>'
               f'</g></g>')

    def bird(x, y, size, dur, delay):
        return (f'<g transform="translate({x} {y})"><g class="fly" style="animation-duration:{dur}s;animation-delay:{delay}s">'
                f'<g class="drift"><text class="bd fl" style="font-size:{size}px">\\v/</text>'
                f'<text class="bd fl2" style="font-size:{size}px">-v-</text></g></g></g>')

    body = runners + bird(500, 16, 14, 14, 2) + bird(560, 30, 11, 17, 6)
    style = fonts(mono=ASCII) + f"""
.a{{font:400 14px {MONO};fill:{c["ink"]};white-space:pre}}.m{{font:400 14px {MONO};fill:{c["muted"]};white-space:pre}}
.bd{{font-family:{MONO};fill:{c["muted"]};white-space:pre}}
{FRAMES.format(t=".45s")}
.fl{{animation:fa .4s steps(1) infinite}}.fl2{{opacity:0;animation:fb .4s steps(1) infinite}}
.run{{animation:run 12s linear infinite}}@keyframes run{{from{{transform:translateX(-440px)}}to{{transform:translateX(480px)}}}}
.bob{{animation:bob .45s ease-in-out infinite alternate}}@keyframes bob{{to{{transform:translateY(-2px)}}}}
.fly{{animation:fly 14s linear infinite backwards}}@keyframes fly{{from{{transform:translateX(260px)}}to{{transform:translateX(-600px)}}}}
.drift{{animation:drift 1.4s ease-in-out infinite alternate}}@keyframes drift{{to{{transform:translateY(4px)}}}}"""
    return svg(720, 84, "A cat chasing a mouse, with birds flying overhead", style, body)


def render_footer(theme):
    """Nap time: a sleeping cat, a panda with its bamboo, a coffee, a hopping bunny and the mouse that got away."""
    c = THEMES[theme]
    def panda(x):
        """Ears and eye patches in dense @ so it reads as a panda. It blinks and chews,
        and its bamboo sways."""
        head = ascii_art([" @@.-'''-.@@", " @/       \\@", " | @@@ @@@ |"], x, 26, "a")
        eyes_open, eyes_shut = ascii_art([" | @o@ @o@ |"], x, 74, "a"), ascii_art([" | @-@ @-@ |"], x, 74, "a")
        nose = ascii_art(["  \\  .v.  /"], x, 90, "a")
        chew_a, chew_b = ascii_art(["   '-._.-'"], x, 106, "a"), ascii_art(["   '-.o.-'"], x, 106, "a")
        leaves = ascii_art(["\\|/"], x + 116, 26, "bb")
        return (head + f'<g class="open">{eyes_open}</g><g class="shut">{eyes_shut}</g>' + nose
                + f'<g class="ca">{chew_a}</g><g class="cb">{chew_b}</g>'
                + f'<g class="leaf">{leaves}</g>' + ascii_art([" |", " +", " |", " +", " |"], x + 116, 42, "bb"))

    zs = "".join(f'<text class="z" x="{92 + i * 7}" y="{66 - i * 4}" style="animation-delay:{-i * 1.2}s;'
                 f'font-size:{11 + i * 2}px">{ch}</text>' for i, ch in enumerate("zzZ"))
    steam = "".join(f'<text class="st" x="306" y="{58 - i * 14}" style="animation-delay:{-i * 1.2}s" '
                    f'xml:space="preserve">{esc(line)}</text>' for i, line in enumerate(["( (", " ) )"]))
    body = f"""<path d="M0 112.5H720" stroke="{c["faint"]}" stroke-dasharray="2 6"/>
{ascii_art([" /\\_/\\", "( -.- )", " > ^ <"], 24, 74, "a")}{zs}
{steam}{ascii_art(["._____.", "|     |]", "\\_____/"], 300, 74, "mug")}
{panda(150)}
<g transform="translate(470 0)"><g class="stroll"><g class="hop">{ascii_art(["(\\_/)", "(o.o)", "(\")(\")"], 0, 74, "a")}</g></g></g>
<g transform="translate(650 0)"><g class="peek">{ascii_art(["<.^__)~"], 0, 106, "m")}</g></g>"""
    style = fonts(mono=ASCII) + f"""
.a{{font:400 14px {MONO};fill:{c["ink"]};white-space:pre}}.m{{font:400 14px {MONO};fill:{c["muted"]};white-space:pre}}
.mug{{font:400 14px {MONO};fill:{c["amber"]};white-space:pre}}
.z{{font-family:{MONO};fill:{c["accent"]};animation:z 3.6s ease-out infinite}}
@keyframes z{{0%{{opacity:0;transform:translate(0,0)}}20%{{opacity:1}}100%{{opacity:0;transform:translate(10px,-30px)}}}}
.st{{font:400 14px {MONO};fill:{c["muted"]};white-space:pre;animation:st 2.4s ease-out infinite}}
@keyframes st{{0%{{opacity:0;transform:translateY(8px)}}35%{{opacity:.9}}100%{{opacity:0;transform:translateY(-10px)}}}}
.hop{{animation:hop .8s cubic-bezier(.3,0,.7,1) infinite}}@keyframes hop{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-12px)}}}}
.stroll{{animation:stroll 7s ease-in-out infinite alternate}}@keyframes stroll{{to{{transform:translateX(110px)}}}}
.bb{{font:400 14px {MONO};fill:{c["green"]};white-space:pre}}
.open{{animation:open 6s infinite}}@keyframes open{{0%,88%{{opacity:1}}88.5%,93%{{opacity:0}}93.5%,100%{{opacity:1}}}}
.shut{{opacity:0;animation:shut 6s infinite}}@keyframes shut{{0%,88%{{opacity:0}}88.5%,93%{{opacity:1}}93.5%,100%{{opacity:0}}}}
.ca{{animation:fa .5s steps(1) infinite}}.cb{{opacity:0;animation:fb .5s steps(1) infinite}}
@keyframes fa{{50%{{opacity:0}}}}@keyframes fb{{50%{{opacity:1}}}}
.leaf{{transform-box:fill-box;transform-origin:50% 100%;animation:sway 2.2s ease-in-out infinite alternate}}
@keyframes sway{{from{{transform:rotate(-8deg)}}to{{transform:rotate(8deg)}}}}
.peek{{animation:peek 8s ease-in-out infinite}}
@keyframes peek{{0%,40%{{transform:translateX(90px)}}50%,75%{{transform:translateX(0)}}85%,100%{{transform:translateX(90px)}}}}"""
    return svg(720, 118, "A napping cat, a panda munching bamboo, a coffee, a hopping bunny and the mouse that got away", style, body)


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


# -------------------------------------------------------------- link buttons

LINKS = [
    ("scholar", "Google Scholar", "si:googlescholar"),
    ("linkedin", "LinkedIn", "linkedin"),
    ("orcid", "ORCID", "si:orcid"),
    ("email", "Email", "email"),
]
BUTTON_THEMES = {"dark": dict(bg="#212830", border="#3d444d", text="#f0f6fc"),
                 "light": dict(bg="#f6f8fa", border="#d1d9e0", text="#25292e")}


@functools.lru_cache(maxsize=None)
def _metrics(weight):
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(_font_bytes("sans", weight)), recalcTimestamp=False)
    return font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm


def text_width(text, size, weight):
    cmap, hmtx, upm = _metrics(weight)
    return sum(hmtx[cmap[ord(ch)]][0] for ch in text) * size / upm


def _button_icon(kind, theme):
    """A 16px icon at the origin."""
    c = THEMES[theme]
    if kind == "eye":
        return (f'<path d="M1 8s2.6-5 7-5 7 5 7 5-2.6 5-7 5-7-5-7-5z" fill="none" stroke="{c["muted"]}" '
                f'stroke-width="1.4" stroke-linejoin="round"/><circle cx="8" cy="8" r="2.2" fill="{c["muted"]}"/>')
    if kind == "email":
        return (f'<rect x="1" y="3" width="14" height="10" rx="2" fill="none" stroke="{c["muted"]}" stroke-width="1.4"/>'
                f'<path d="M1.8 4.2L8 8.8l6.2-4.6" fill="none" stroke="{c["muted"]}" stroke-width="1.4" stroke-linejoin="round"/>')
    if kind == "linkedin":
        return ('<rect width="16" height="16" rx="3" fill="#0a66c2"/>'
                '<text x="8" y="12.2" class="in">in</text>')
    slug = kind[3:]
    path = re.search(r'<path d="([^"]+)"', fetch(f"{SIMPLE_ICONS}/icons/{slug}.svg").decode()).group(1)
    return f'<path transform="scale(.6667)" d="{path}" fill="#{_simple_icons_meta()[slug]}"/>'


def render_button(theme, label, icon):
    b = BUTTON_THEMES[theme]
    size, height = 14, 28
    width = round(36 + text_width(label, size, 500) + 13)
    style = fonts(sans500=label, sans600="in" if icon == "linkedin" else "") + f"""
.lb{{font:500 {size}px {SANS};fill:{b["text"]}}}
.in{{font:600 11px {SANS};fill:#fff;text-anchor:middle}}"""
    body = f"""<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="6" fill="{b["bg"]}" stroke="{b["border"]}"/>
<g transform="translate(12 6)">{_button_icon(icon, theme)}</g>
<text class="lb" x="36" y="19">{esc(label)}</text>"""
    return svg(width, height, label, style, body)


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


def picture(dark, light, attrs):
    """A <picture> that swaps to the dark image on dark themes."""
    return (f'<picture><source media="(prefers-color-scheme: dark)" srcset="{dark}">'
            f'<img src="{light}" {attrs}></picture>')


def tool_file(tool, theme):
    return f"assets/tools/{tool.replace(':', '-')}-{theme}.svg"


def render_tool(theme, icon, name, pop_delay, wave_delay):
    """One icon, 37px on a 43x45 canvas that leaves room for the ripple."""
    style = """.pop{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.2,.8,.3,1.25) backwards}
@keyframes pop{from{opacity:0;transform:scale(.6)}}
.wave{animation:wave 8s ease-in-out infinite}
@keyframes wave{0%,10%,100%{transform:translateY(0)}5%{transform:translateY(-5px)}}"""
    body = (f'<g class="pop" style="animation-delay:{pop_delay:.3f}s"><g class="wave" style="animation-delay:{wave_delay:.2f}s">'
            f'<g transform="translate(3 5) scale({37 / 256:.5f})">{icon}</g></g></g>')
    return svg(43, 45, name, style, body)


def render_tool_label(theme, label):
    c = THEMES[theme]
    style = fonts(sans400=label) + f".lb{{font:400 13px {SANS};fill:{c['muted']}}}"
    return svg(118, 45, label, style, f'<text class="lb" x="0" y="28">{esc(label)}</text>')


def write_tools():
    """Write every icon and label image, and return the README block that lays them out."""
    out = ASSETS / "tools"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.svg"):
        old.unlink()
    for theme in THEMES:
        icons = _skill_icons([t for _, row in TOOLS for t, _ in row if not t.startswith("si:")], theme)
        n = 0
        for r, (label, row) in enumerate(TOOLS):
            (ROOT / tool_file(f"row{r}", theme)).write_text(render_tool_label(theme, label))
            for col, (tool, name) in enumerate(row):
                icon = _simple_icon(tool[3:], theme) if tool.startswith("si:") else icons[tool]
                svg_text = render_tool(theme, icon, name, 0.2 + n * 0.025, 1.8 + col * 0.08 + r * 0.3)
                (ROOT / tool_file(tool, theme)).write_text(svg_text)
                n += 1
    rows = []
    for r, (label, row) in enumerate(TOOLS):
        cells = [picture(tool_file(f"row{r}", "dark"), tool_file(f"row{r}", "light"), f'height="45" alt="{esc(label)}"')]
        cells += [picture(tool_file(t, "dark"), tool_file(t, "light"), f'height="45" alt="{esc(name)}" title="{esc(name)}"')
                  for t, name in row]
        rows.append("".join(cells) + "<br>")
    return "\n".join(rows)


def fetch_views():
    """Total profile views. The README shows the counter as an invisible pixel, which
    keeps counting visits; this reads the total once a night for the matching button."""
    counts = re.findall(r">([\d,]+)<", fetch(f"https://komarev.com/ghpvc/?username={LOGIN}").decode())
    return int(counts[-1].replace(",", ""))


def views_label(n):
    return f"{n / 1000:.1f}K profile views" if n >= 10_000 else f"{n:,} profile views"


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


WEEK_W, WEEK_H, BAR_SPAN = 13, 50, 44


def render_activity_stats(theme, stats):
    c = THEMES[theme]
    total, current, longest, _ = stats
    figures = [
        (f"{total:,}", "contributions in the past year"),
        (plural(current, "day"), "current streak"),
        (plural(longest, "day"), "longest streak"),
    ]
    parts, sans_600, sans_400 = [], "", ""
    for i, (value, label) in enumerate(figures):
        x = i * 240
        parts.append(f'<text class="v" x="{x}" y="32">{esc(value)}</text>')
        dx = 12 if i == 1 and current else 0
        if dx:
            parts.append(f'<circle class="live" cx="{x + 4}" cy="49.5" r="4" fill="{c["green"]}"/>')
        parts.append(f'<text class="l" x="{x + 1 + dx}" y="54">{esc(label)}</text>')
        sans_600 += value
        sans_400 += label
    style = fonts(sans_600, sans_400) + f"""
.v{{font:600 26px {SANS};fill:{c["ink"]};letter-spacing:-.01em}}
.l{{font:400 14px {SANS};fill:{c["muted"]}}}
.live{{animation:glow 1.6s ease-in-out infinite}}@keyframes glow{{50%{{opacity:.45}}}}"""
    return svg(720, 68, activity_summary(stats), style, "\n".join(parts))


def render_week(theme, i, n, peak, last):
    c = THEMES[theme]
    h = max(2.0, BAR_SPAN * (n / peak) ** 0.5) if n else 2.0
    cls = "bar now" if last and n else "bar" if n else "nil"
    style = f"""
.bar{{fill:{c["accent"]}}}.nil{{fill:{c["faint"]}}}
.bar,.nil{{transform-box:fill-box;transform-origin:50% 100%;animation:grow .7s cubic-bezier(.2,.7,.2,1) backwards}}
.now{{animation:grow .7s cubic-bezier(.2,.7,.2,1) backwards,glow 2.4s 1.5s ease-in-out infinite}}
@keyframes grow{{from{{transform:scaleY(0)}}}}@keyframes glow{{50%{{opacity:.45}}}}"""
    body = (f'<rect class="{cls}" style="animation-delay:{0.2 + i * 0.012:.3f}s" x="1.5" y="{2 + BAR_SPAN - h:.1f}" '
            f'width="{WEEK_W - 3}" height="{h:.1f}" rx="1.5"/>')
    return svg(WEEK_W, WEEK_H, plural(n, "contribution"), style, body)


def render_months(theme, weeks):
    c = THEMES[theme]
    parts, text, last_month = [], "", None
    for i, (start, _) in enumerate(weeks):
        month = dt.date.fromisoformat(start).strftime("%b")
        if month != last_month and i < len(weeks) - 2:
            if last_month is not None:  # skip the partial month at the left edge
                parts.append(f'<text class="mo" x="{i * WEEK_W + 1.5}" y="14">{month}</text>')
                text += month
            last_month = month
    style = fonts(sans400=text) + f".mo{{font:400 12px {SANS};fill:{c['muted']}}}"
    return svg(WEEK_W * len(weeks), 20, "Months", style, "\n".join(parts))


def activity_summary(stats):
    total, current, longest, weeks = stats
    busiest = max(weeks, key=lambda w: w[1])
    return (f"{total:,} contributions in the past year. Current streak {plural(current, 'day')}, "
            f"longest streak {plural(longest, 'day')}. Busiest: {plural(busiest[1], 'contribution')} "
            f"in the week of {week_label(busiest[0])}.")


def week_label(start):
    return dt.date.fromisoformat(start).strftime("%-d %b %Y")


def write_activity(stats):
    """Write the stats, week and month images, and return the README block for them."""
    total, current, longest, weeks = stats
    out = ASSETS / "activity"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.svg"):
        old.unlink()
    peak = max((n for _, n in weeks), default=0) or 1
    for theme in THEMES:
        (out / f"stats-{theme}.svg").write_text(render_activity_stats(theme, stats))
        (out / f"months-{theme}.svg").write_text(render_months(theme, weeks))
        for i, (_, n) in enumerate(weeks):
            (out / f"week-{i:02d}-{theme}.svg").write_text(render_week(theme, i, n, peak, i == len(weeks) - 1))
    summary = esc(activity_summary(stats))
    bars = []
    for i, (start, n) in enumerate(weeks):
        tip = esc(f"Week of {week_label(start)}: {plural(n, 'contribution')}")
        bars.append(picture(f"assets/activity/week-{i:02d}-dark.svg", f"assets/activity/week-{i:02d}-light.svg",
                            f'height="{WEEK_H}" alt="{tip}" title="{tip}"'))
    bars = "".join(bars)
    return "\n".join([
        picture("assets/activity/stats-dark.svg", "assets/activity/stats-light.svg",
                f'width="720" alt="{summary}" title="{summary}"') + "<br>",
        bars + "<br>",
        picture("assets/activity/months-dark.svg", "assets/activity/months-light.svg",
                f'height="20" alt="Months"'),
    ])


def update_readme(section, block):
    """Replace the text between <!-- section:start --> and <!-- section:end --> in README.md."""
    readme = ROOT / "README.md"
    text = readme.read_text()
    start, end = f"<!-- {section}:start -->", f"<!-- {section}:end -->"
    i, j = text.index(start) + len(start), text.index(end)
    readme.write_text(text[:i] + "\n" + block + "\n" + text[j:])


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "static":
        for theme in THEMES:
            (ASSETS / f"hero-{theme}.svg").write_text(render_hero(theme))
            (ASSETS / f"animals-chase-{theme}.svg").write_text(render_chase(theme))
            (ASSETS / f"animals-nap-{theme}.svg").write_text(render_footer(theme))
            for key, title, lines, stage in WORK:
                (ASSETS / f"work-{key}-{theme}.svg").write_text(tile(theme, title, lines, stage))
            for key, label, icon in LINKS:
                (ASSETS / f"link-{key}-{theme}.svg").write_text(render_button(theme, label, icon))
        update_readme("tools", write_tools())
    elif what == "activity":
        stats = summarise(*fetch_contributions())
        update_readme("activity", write_activity(stats))
        print(activity_summary(stats))
        try:
            views = fetch_views()
        except (OSError, ValueError, IndexError) as e:
            print(f"Views button not updated: {e}")
        else:
            for theme in THEMES:
                (ASSETS / f"link-views-{theme}.svg").write_text(render_button(theme, views_label(views), "eye"))
            print(views_label(views))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
