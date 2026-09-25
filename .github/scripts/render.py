#!/usr/bin/env python3
"""Render the profile SVGs in assets/ (a dark and a light copy of each).

    python .github/scripts/render.py hero       # static header; rerun after editing HERO_*
    python .github/scripts/render.py activity   # needs GITHUB_TOKEN; the workflow runs it daily

IBM Plex (SIL Open Font License) is fetched from google/fonts and embedded as a
subset, so the images look the same on every OS. Needs: pip install fonttools brotli
"""

import base64
import datetime as dt
import html
import io
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
LOGIN = "ips610"

HERO_NAME = "Ishpuneet Singh"
HERO_ROLE = "Cybersecurity and machine learning researcher"
# Each line is exactly 15 characters, so with its newline it fills one 16-byte
# hexdump row and the ASCII column ends every row with "." (0x0a).
HERO_LINES = ["binary analysis", "user biometrics", "medical imaging", "network defense"]

# GitHub Primer colours, so the images sit naturally on either theme.
THEMES = {
    "dark": dict(ink="#f0f6fc", muted="#9198a1", faint="#3d444d", byte="#79c0ff",
                 space="#656c76", newline="#d29922", bar="#4493f8"),
    "light": dict(ink="#1f2328", muted="#59636e", faint="#d1d9e0", byte="#0969da",
                  space="#9198a1", newline="#9a6700", bar="#0969da"),
}

FONT_CACHE = Path(os.environ.get("FONT_CACHE", Path.home() / ".cache" / "ips610-fonts"))
FONT_SOURCES = {
    "sans": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsans/IBMPlexSans%5Bwdth,wght%5D.ttf",
    "mono": "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
}
FALLBACK = {
    "sans": '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif',
    "mono": 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
}


# --------------------------------------------------------------------- fonts

def _font_file(source):
    FONT_CACHE.mkdir(parents=True, exist_ok=True)
    path = FONT_CACHE / f"{source}.ttf"
    if not path.exists():
        with urllib.request.urlopen(FONT_SOURCES[source], timeout=60) as r:
            path.write_bytes(r.read())
    return path


def font_face(family, source, weight, text):
    """@font-face rule with a woff2 subset of `source` covering `text`."""
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = TTFont(_font_file(source))
    if "fvar" in font:
        font = instancer.instantiateVariableFont(font, {"wght": weight, "wdth": 100})
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
    return (f'@font-face{{font-family:"{family}";font-weight:{weight};'
            f'src:url(data:font/woff2;base64,{data}) format("woff2")}}')


def esc(s):
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------- hero

def render_hero(theme):
    c = THEMES[theme]
    data = "".join(line + "\n" for line in HERO_LINES).encode()
    assert all(len(line) == 15 for line in HERO_LINES), "each hero line must be 15 chars"

    size, adv = 15, 9  # Plex Mono advance is 0.6em
    x_hex, x_bar = 90, 540
    x_ascii = x_bar + adv
    y0, lh = 152, 26

    def hex_x(i):
        return x_hex + i * 3 * adv + (adv if i >= 8 else 0)

    parts, mono_text = [], "0123456789abcdef|."
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
            mono_text += ch
            delay = f"{0.35 + i * 0.028:.3f}s"
            parts.append(f'<text class="m {kind} hx" x="{hex_x(col)}" y="{y}" '
                         f'style="animation-delay:{delay}">{b:02x}</text>')
            if ch != " ":
                parts.append(f'<text class="m {kind} dec" x="{x_ascii + col * adv}" y="{y}" '
                             f'style="animation-delay:{delay}">{esc(ch)}</text>')
    end_y = y0 + (len(data) // 16) * lh
    parts.append(f'<text class="m off" x="2" y="{end_y}">{len(data):08x}</text>')

    width, height = 720, end_y + 22
    fonts = "".join([
        font_face("HeroSans", "sans", 600, HERO_NAME),
        font_face("HeroSans", "sans", 400, HERO_ROLE),
        font_face("HeroMono", "mono", 400, mono_text),
    ])
    desc = (f"{HERO_ROLE}. A hexdump whose text column reads: "
            + ", ".join(HERO_LINES) + ".")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">
<title id="t">{esc(HERO_NAME)}</title>
<desc id="d">{esc(desc)}</desc>
<style>
{fonts}
.name{{font:600 50px HeroSans,{FALLBACK["sans"]};fill:{c["ink"]};letter-spacing:-.02em}}
.role{{font:400 19px HeroSans,{FALLBACK["sans"]};fill:{c["muted"]}}}
.m{{font:400 {size}px HeroMono,{FALLBACK["mono"]}}}
.off{{fill:{c["space"]}}}.b{{fill:{c["byte"]}}}.sp{{fill:{c["space"]}}}.nl{{fill:{c["newline"]}}}
.hx{{animation:hx .4s ease-out backwards}}.dec{{animation:dec .4s ease-out backwards}}
@keyframes hx{{from{{opacity:.2}}}}@keyframes dec{{from{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.hx,.dec{{animation:none}}}}
</style>
<text class="name" x="0" y="60">{esc(HERO_NAME)}</text>
<text class="role" x="1" y="98">{esc(HERO_ROLE)}</text>
{chr(10).join(parts)}
</svg>
"""


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


def fetch():
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
        parts.append(f'<text class="l" x="{x + 1}" y="54">{esc(label)}</text>')
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
        parts.append(f'<rect class="{cls}" x="{x:.1f}" y="{top + span - h:.1f}" '
                     f'width="{pitch - 3:.1f}" height="{h:.1f}" rx="1.5"><title>'
                     f'{plural(n, "contribution")} in the week of {start}</title></rect>')
        month = dt.date.fromisoformat(start).strftime("%b")
        if month != last_month and i < len(weeks) - 2:
            if last_month is not None:  # skip the partial month at the left edge
                parts.append(f'<text class="mo" x="{x:.1f}" y="{top + span + 22}">{month}</text>')
                sans_400 += month
            last_month = month

    fonts = font_face("CardSans", "sans", 600, sans_600) + font_face("CardSans", "sans", 400, sans_400)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t">
<title id="t">{total:,} contributions in the past year; current streak {plural(current, "day")}; longest streak {plural(longest, "day")}</title>
<style>
{fonts}
.v{{font:600 26px CardSans,{FALLBACK["sans"]};fill:{c["ink"]};letter-spacing:-.01em}}
.l{{font:400 14px CardSans,{FALLBACK["sans"]};fill:{c["muted"]}}}
.mo{{font:400 12px CardSans,{FALLBACK["sans"]};fill:{c["muted"]}}}
.bar{{fill:{c["bar"]}}}.nil{{fill:{c["faint"]}}}
</style>
{chr(10).join(parts)}
</svg>
"""


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "hero":
        for theme in THEMES:
            (ASSETS / f"hero-{theme}.svg").write_text(render_hero(theme))
    elif what == "activity":
        stats = summarise(*fetch())
        for theme in THEMES:
            (ASSETS / f"activity-{theme}.svg").write_text(render_activity(theme, stats))
        print(f"{stats[0]} contributions, current streak {stats[1]}, longest {stats[2]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
