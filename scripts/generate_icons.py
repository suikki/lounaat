"""Generate PWA + favicon PNGs from the same design as docs/icons/icon.svg.

Run this once (or whenever the brand color/icon changes):

    python scripts/generate_icons.py

Outputs:
    docs/icons/icon-192.png
    docs/icons/icon-512.png
    docs/icons/apple-touch-icon.png    (180×180 for iOS)
    docs/icons/favicon-32.png          (small browser tab icon)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


# Brand colour (matches --accent in docs/style.css and fill in docs/icons/icon.svg).
BG = (214, 90, 49, 255)        # #d65a31
WHITE = (255, 255, 255, 255)

# Geometry expressed in fractions of canvas size — matches the 512-px SVG:
# x=160 → 160/512 ≈ 0.3125 ; thickness 68/512 ≈ 0.133 ; etc.
CORNER_RADIUS = 96 / 512        # rounded square
L_LEFT = 160 / 512
L_THICKNESS = 68 / 512
L_TOP = 112 / 512
L_BOTTOM = 400 / 512
L_RIGHT = 404 / 512


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = int(size * CORNER_RADIUS)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    # Vertical bar of the L
    x0 = int(size * L_LEFT)
    y0 = int(size * L_TOP)
    x1 = x0 + int(size * L_THICKNESS)
    y1 = int(size * L_BOTTOM)
    draw.rectangle([x0, y0, x1, y1], fill=WHITE)

    # Horizontal bar of the L
    by0 = y1 - int(size * L_THICKNESS)
    bx1 = int(size * L_RIGHT)
    draw.rectangle([x0, by0, bx1, y1], fill=WHITE)

    return img


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "docs" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),
        ("favicon-32.png", 32),
    ]
    for name, size in targets:
        make_icon(size).save(out / name, optimize=True)
        print(f"wrote {out / name} ({size}×{size})")


if __name__ == "__main__":
    main()
