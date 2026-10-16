#!/usr/bin/env python3
"""Build the devboard logo (light and dark SVG), the favicon and a social preview from Nunito Sans.

The wordmark is converted to outlines, so the SVG looks the same everywhere (GitHub serves SVGs as
images, without web fonts). The mascot is an original pixel critter holding a kanban card.
    python3 docs/make-logo.py
"""
import io
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "skills" / "devboard" / "web" / "fonts" / "nunito-sans.woff2"
OUT = ROOT / "docs" / "brand"
SIZE, BASE, TRACK = 112.0, 150.0, -2.0          # font size (px), baseline y, extra letter spacing
THEMES = {
    "light": {"dev": "#0f7a63", "board": "#15302a", "body": "#d97757", "shade": "#b9603f", "eye": "#2b1912",
              "card": "#ffffff", "card_line": "#cfdcd7", "tick": "#0f9b82", "blush": "#f2a98d"},
    "dark":  {"dev": "#4fd1b0", "board": "#e6efed", "body": "#e58a6a", "shade": "#c66f50", "eye": "#2b1912",
              "card": "#1d2b28", "card_line": "#3b524c", "tick": "#4fd1b0", "blush": "#f5b39b"},
}

# 11 x 8 pixel critter, sitting: "B" body, "S" shade, "E" eye, "P" blush, "." empty
CRITTER = [
    "..BBBBBBB..",
    ".BBBBBBBBB.",
    "BBBEBBBEBBB",
    "BBBEBBBEBBB",
    "BBPBBBBBPBB",
    ".BBBBBBBBB.",
    ".SSSSSSSSS.",
    "..S..S..S..",
]


def wordmark():
    tt = TTFont(io.BytesIO(FONT.read_bytes()))
    if "fvar" in tt:
        tt = instantiateVariableFont(tt, {"wght": 900}, inplace=False)
    cmap, gs, hmtx = tt.getBestCmap(), tt.getGlyphSet(), tt["hmtx"]
    scale = SIZE / tt["head"].unitsPerEm
    x, glyphs = 8.0, []
    for ch in "devboard":
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, BASE)))
        bounds = BoundsPen(gs)
        gs[name].draw(TransformPen(bounds, (scale, 0, 0, -scale, x, BASE)))
        glyphs.append((ch, pen.getCommands(), bounds.bounds))
        x += hmtx[name][0] * scale + TRACK
    return glyphs, x


def critter(t, x0, y0, p, card_on=True):
    """Pixels of the critter with its top-left at (x0, y0), one pixel = p px, plus the card it holds."""
    color = {"B": t["body"], "S": t["shade"], "E": t["eye"], "P": t["blush"]}
    # one path per colour: squares of the same path share edges, so no hairline seams between pixels
    rects = []
    for key, fill in color.items():
        d = "".join(f"M{x0 + c * p:.2f} {y0 + r * p:.2f}h{p:.2f}v{p:.2f}h-{p:.2f}z"
                    for r, row in enumerate(CRITTER) for c, ch in enumerate(row) if ch == key)
        if d:
            rects.append(f'<path d="{d}" fill="{fill}"/>')
    # the card: tilted, held against the right side of the body
    cx, cy, w, h = x0 + 9.2 * p, y0 + 1.6 * p, 4.6 * p, 5.6 * p
    card = (f'<g transform="rotate(12 {cx + w / 2:.1f} {cy + h / 2:.1f})">'
            f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{p * 0.6:.1f}" fill="{t["card"]}" stroke="{t["card_line"]}" stroke-width="{p * 0.35:.1f}"/>'
            f'<rect x="{cx + p * 0.8:.1f}" y="{cy + p * 0.9:.1f}" width="{w - p * 1.6:.1f}" height="{p * 0.55:.1f}" rx="{p * 0.27:.1f}" fill="{t["card_line"]}"/>'
            f'<path d="M{cx + p * 1.0:.1f} {cy + h * 0.62:.1f} l{p * 0.9:.1f} {p * 0.9:.1f} l{p * 1.9:.1f} -{p * 2.0:.1f}" fill="none" stroke="{t["tick"]}" stroke-width="{p * 0.6:.1f}" stroke-linecap="round" stroke-linejoin="round"/></g>')
    if not card_on:
        return "".join(rects)
    hand = f'<path d="M{x0 + 10 * p:.2f} {y0 + 4 * p:.2f}h{p * 1.2:.2f}v{p * 1.2:.2f}h-{p * 1.2:.2f}z" fill="{t["body"]}"/>'
    return "".join(rects) + card + hand


def logo(theme):
    t = THEMES[theme]
    glyphs, width = wordmark()
    paths = "".join(f'<path d="{d}" fill="{t["dev"] if i < 3 else t["board"]}"/>' for i, (_, d, _) in enumerate(glyphs))
    _, _, (dx0, dy0, dx1, _) = glyphs[-1]              # last "d": the critter sits on its ascender
    p = 6.2
    cx = dx1 - 0.075 * SIZE - 5.5 * p                  # body centred over the stem of the "d"
    cy = dy0 - 8 * p + 0.6 * p                         # feet resting on top of the ascender
    w = max(width, cx + 15 * p) + 8
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {cy - 6:.0f} {w:.0f} {BASE - cy + 36:.0f}" '
            f'width="{w * 0.9:.0f}" role="img" aria-label="devboard"><title>devboard</title>'
            f'{paths}{critter(t, cx, cy, p)}</svg>\n')


def favicon():
    t = THEMES["light"]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -2 13 12"><title>devboard</title>'
            f'{critter(t, 0, 0, 1, card_on=False)}</svg>\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "logo.svg").write_text(logo("light"), encoding="utf-8")
    (OUT / "logo-dark.svg").write_text(logo("dark"), encoding="utf-8")
    fav = favicon()
    (OUT / "mark.svg").write_text(fav, encoding="utf-8")
    (ROOT / "skills" / "devboard" / "web" / "favicon.svg").write_text(fav, encoding="utf-8")
    print("written:", sorted(p.name for p in OUT.glob("*.svg")), "+ web/favicon.svg")


if __name__ == "__main__":
    main()
