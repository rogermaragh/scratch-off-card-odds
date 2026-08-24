#!/usr/bin/env python3
"""Generate the app icon from code, so it can be changed without a design tool.

The mark is the app's own language: a gold ticket stub, notched at the sides,
with three scoreboard tiles above a perforated tear line. At 1024 it reads as a
lottery ticket; at 60 the silhouette — a pinched gold rectangle with three dark
bars — still separates it from every other icon on a home screen.

    python3 Scripts/make_icon.py            # writes the asset catalog
    python3 Scripts/make_icon.py --preview  # also writes a contact sheet
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "Resources" / "Assets.xcassets" / "AppIcon.appiconset"
MARKETING = ROOT / "marketing" / "icon"

INK = (17, 17, 19)          # near-black, same family as the display strip
GOLD = (250, 199, 49)       # the accent used for special balls
GOLD_DEEP = (214, 165, 28)  # a hair darker, for the stub's lower half

# Supersample, then downsample: gives clean curves without antialiasing tricks.
SCALE = 4


def rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render(size: int) -> Image.Image:
    """Draw the stub on its own layer, then mask and rotate it.

    Painting the two-tone halves directly onto the background left artifacts
    where the lower band met the rounded corners. Building the stub as a masked
    layer keeps the silhouette exact, and lets it tilt.
    """
    s = size * SCALE
    img = Image.new("RGB", (s, s), INK)

    # Ticket proportions: wider than tall, so it does not read as a slab.
    w, h = s * 0.74, s * 0.58
    radius = h * 0.13

    layer = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=GOLD + (255,))

    # Lower band drawn with square corners, then the whole layer is clipped
    # back to the rounded silhouette. Pasting a masked band instead punched a
    # hole in the gold, because the band's transparent top overwrote it.
    tear_y = h * 0.60
    d.rectangle((0, tear_y, w, h), fill=GOLD_DEEP + (255,))

    clip = Image.new("L", (int(w), int(h)), 0)
    ImageDraw.Draw(clip).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    layer.putalpha(clip)

    d = ImageDraw.Draw(layer)

    # Three scoreboard tiles: the silhouette that has to survive to 29pt.
    tile_w = w * 0.205
    tile_h = h * 0.36
    tile_gap = w * 0.052
    total = tile_w * 3 + tile_gap * 2
    left = (w - total) / 2
    top = h * 0.11
    for i in range(3):
        x0 = left + i * (tile_w + tile_gap)
        d.rounded_rectangle((x0, top, x0 + tile_w, top + tile_h),
                            radius=w * 0.022, fill=INK + (255,))

    # Perforation dots along the tear.
    dot_r = w * 0.010
    gap = w * 0.058
    x = gap
    while x < w - gap * 0.5:
        d.ellipse((x - dot_r, tear_y - dot_r, x + dot_r, tear_y + dot_r),
                  fill=INK + (255,))
        x += gap

    # A hint of a serial line in the stub half.
    bar_y = tear_y + (h - tear_y) * 0.55
    bar_h = h * 0.045
    d.rounded_rectangle((w * 0.24, bar_y, w * 0.76, bar_y + bar_h),
                        radius=bar_h / 2, fill=INK + (110,))

    # Side notches, punched clean through the layer's alpha.
    notch_r = h * 0.11
    for cx in (0, w):
        d.ellipse((cx - notch_r, tear_y - notch_r, cx + notch_r, tear_y + notch_r),
                  fill=(0, 0, 0, 0))

    # A slight tilt reads as motion rather than a filed document.
    layer = layer.rotate(-8, resample=Image.BICUBIC, expand=True)
    img.paste(layer, ((s - layer.width) // 2, (s - layer.height) // 2), layer)

    return img.resize((size, size), Image.LANCZOS)


def main():
    preview = "--preview" in sys.argv

    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = render(1024)
    icon.save(ASSETS / "icon-1024.png")

    # Xcode 14+ accepts a single 1024 source and derives the rest.
    (ASSETS / "Contents.json").write_text(json.dumps({
        "images": [{"filename": "icon-1024.png", "idiom": "universal",
                    "platform": "ios", "size": "1024x1024"}],
        "info": {"author": "xcode", "version": 1},
    }, indent=2))

    MARKETING.mkdir(parents=True, exist_ok=True)
    icon.save(MARKETING / "icon-1024.png")
    for size in (180, 120, 87, 60):
        render(size).save(MARKETING / f"icon-{size}.png")

    if preview:
        # A contact sheet makes small-size legibility obvious at a glance.
        sizes = [180, 120, 87, 60, 40, 29]
        sheet = Image.new("RGB", (sum(sizes) + 20 * len(sizes), 220), (245, 245, 247))
        x = 10
        for size in sizes:
            sheet.paste(render(size), (x, (220 - size) // 2))
            x += size + 20
        sheet.save(MARKETING / "contact-sheet.png")
        print(f"preview → {MARKETING / 'contact-sheet.png'}")

    print(f"icon → {ASSETS / 'icon-1024.png'}")


if __name__ == "__main__":
    main()
