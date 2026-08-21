"""Rasterize favicon.svg to standard PNG sizes using Edge's headless renderer.

Edge (Chromium) rasterizes the SVG faithfully. Headless screenshots composite
onto an opaque page background, so we render each canvas twice (over pure
white and pure black) and recover a true, anti-aliased RGBA image from the
difference -- alpha = 1 - (white - black)/255 per pixel. This preserves the
rounded-corner transparency and edge anti-aliasing of the brand tile exactly.
"""
import os
import re
import subprocess
import tempfile

from PIL import Image

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(BASE, "static", "images", "favicon.svg")
OUT = os.path.join(BASE, "static", "images")

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# (filename, size, opaque) -- opaque removes corner rounding for the iOS tile.
TARGETS = [
    ("favicon-16x16.png", 16, False),
    ("favicon-32x32.png", 32, False),
    ("favicon-48x48.png", 48, False),
    ("apple-touch-icon.png", 180, True),
    ("grochub-logo.png", 512, False),
]


def build_document(svg_text, size, opaque, bg_hex):
    svg = svg_text
    if opaque:
        svg = svg.replace('rx="14" ry="14"', 'rx="0" ry="0"')
    # Force the inline SVG to fill the target canvas regardless of its attrs.
    svg = re.sub(r' width="[^"]*"\s+height="[^"]*"', "", svg, count=1)
    svg = svg.replace("<svg ", f'<svg width="{size}" height="{size}" ', 1)
    if not opaque:
        svg = svg.replace("<svg ", '<svg style="margin:0;display:block" ', 1)
    return (
        "<!doctype html><html><head><meta charset='utf-8'></head>"
        f"<body style='margin:0;background:#{bg_hex}'>{svg}</body></html>"
    )


def edge_screenshot(html_path, out_path, size):
    cmd = [
        EDGE,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size={size},{size}",
        f"--screenshot={out_path}",
        "file:///" + html_path.replace("\\", "/"),
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"Edge produced no screenshot for {out_path}")


def render_over(svg_text, size, opaque, bg_hex, tag, tmpdir):
    doc = build_document(svg_text, size, opaque, bg_hex)
    html_path = os.path.join(tmpdir, f"frame_{tag}.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    shot_path = os.path.join(tmpdir, f"shot_{tag}.png")
    edge_screenshot(html_path, shot_path, size)
    return Image.open(shot_path).convert("RGB")


def recover_rgba(white, black):
    w = white.load()
    b = black.load()
    sx, sy = white.size
    out = Image.new("RGBA", (sx, sy))
    po = out.load()
    for y in range(sy):
        for x in range(sx):
            wc = w[x, y]
            bc = b[x, y]
            alpha = 255 - ((wc[0] - bc[0]) + (wc[1] - bc[1]) + (wc[2] - bc[2])) // 3
            alpha = max(0, min(255, alpha))
            if alpha:
                rgb = tuple(min(255, round(c * 255.0 / alpha)) for c in bc)
            else:
                rgb = (0, 0, 0)
            po[x, y] = (rgb[0], rgb[1], rgb[2], alpha)
    return out


def main():
    if not os.path.isfile(EDGE):
        raise SystemExit("Edge not found: " + EDGE)
    with open(SVG, encoding="utf-8") as fh:
        svg_text = fh.read()
    tmpdir = tempfile.mkdtemp()
    for name, size, opaque in TARGETS:
        white = render_over(svg_text, size, opaque, "ffffff", name, tmpdir)
        black = render_over(svg_text, size, opaque, "000000", name, tmpdir)
        final = recover_rgba(white, black)
        out_path = os.path.join(OUT, name)
        final.save(out_path, format="PNG")
        corner = final.getpixel((2, 2))
        center = final.getpixel((size // 2, size // 2))
        print("wrote", name, final.size, final.mode,
              "corner=", corner, "center=", center)
        assert final.size == (size, size)


if __name__ == "__main__":
    main()