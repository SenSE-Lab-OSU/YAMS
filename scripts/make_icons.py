#!/usr/bin/env python3
"""Regenerate the platform icons from the master artwork.

    python scripts/make_icons.py

Source of truth is `yams_logo.png` (square, RGBA, transparent background). This
produces:

    yams.ico    multi-size Windows icon (16..256) -> app_windows.spec
    yams.icns   real macOS icon bundle (16..1024) -> app_macos.spec
    yams_favicon.png   32 px, for the Gradio browser tab

The artwork is trimmed to its alpha bounding box and re-centred on a square
canvas before scaling, so the glyph fills the frame consistently instead of
inheriting whatever uneven margins the export happened to have. That matters at
16 px, where the line art is only a pixel or two wide.

Requires Pillow; the .icns step uses macOS `iconutil` and is skipped elsewhere
(the committed .icns is only rebuilt when this is run on a Mac).
"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageFilter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(REPO, "yams", "resources", "icons")
SOURCE = os.path.join(HERE, "yams_logo.png")

MARGIN = 0.06          # fraction of the canvas left clear on each side
BOOST_BELOW = 48       # sizes under this get their strokes thickened
BOOST_RADIUS = 2       # dilation radius, in pixels of an 8x supersample
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SPEC = [          # (pixel size, iconset filename)
    (16, "icon_16x16.png"),      (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),      (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),   (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),   (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),   (1024, "icon_512x512@2x.png"),
]


def normalized(path=SOURCE):
    """Trim to the artwork, then centre it on a square transparent canvas."""
    im = Image.open(path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if bbox is None:
        raise SystemExit(f"{path}: image is fully transparent")
    art = im.crop(bbox)

    side = int(round(max(art.size) / (1 - 2 * MARGIN)))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
    return canvas


def brand_colour(master):
    """Median colour of the opaque pixels — the artwork's single ink colour."""
    px = np.array(master)
    opaque = px[px[..., 3] > 200][:, :3]
    return tuple(int(c) for c in np.median(opaque, axis=0))


def scaled(master, size, colour=None):
    """Downscale to `size`, thickening strokes for the small icons.

    The logo is fine line art: at 16 px a stroke lands well under one pixel and
    LANCZOS renders it as a pale smudge. Below BOOST_BELOW the alpha channel is
    dilated on an 8x supersample first, so the strokes stay solid. Only alpha is
    dilated — running a MinFilter over RGB would drag the colour toward the
    black of the transparent pixels.
    """
    if size >= BOOST_BELOW or colour is None:
        return master.resize((size, size), Image.LANCZOS)

    mid = size * 8
    alpha = (master.resize((mid, mid), Image.LANCZOS)
             .getchannel("A")
             .filter(ImageFilter.MaxFilter(BOOST_RADIUS * 2 + 1)))
    ink = Image.new("RGBA", (mid, mid), colour + (255,))
    ink.putalpha(alpha)
    return ink.resize((size, size), Image.LANCZOS)


def build_ico(master, colour):
    out = os.path.join(HERE, "yams.ico")
    frames = [scaled(master, s, colour) for s in ICO_SIZES]
    # Pillow rescales `sizes` from the base image, which would discard the
    # stroke boost, so hand it the prepared frames via append_images instead.
    frames[-1].save(out, format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                    append_images=frames[:-1])
    return out


def build_favicon(master, colour):
    out = os.path.join(HERE, "yams_favicon.png")
    scaled(master, 32, colour).save(out, format="PNG")
    return out


def build_icns(master, colour):
    if not shutil.which("iconutil"):
        print("  skipped yams.icns (iconutil is macOS-only)")
        return None
    out = os.path.join(HERE, "yams.icns")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "yams.iconset")
        os.makedirs(iconset)
        for size, name in ICNS_SPEC:
            scaled(master, size, colour).save(os.path.join(iconset, name), format="PNG")
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
    return out


if __name__ == "__main__":
    if not os.path.exists(SOURCE):
        raise SystemExit(f"missing source artwork: {SOURCE}")
    master = normalized()
    colour = brand_colour(master)
    print(f"source {SOURCE} -> normalized {master.size[0]}x{master.size[1]}, "
          f"ink #{colour[0]:02X}{colour[1]:02X}{colour[2]:02X}")
    for path in (build_ico(master, colour), build_icns(master, colour),
                 build_favicon(master, colour)):
        if path:
            print(f"  wrote {os.path.relpath(path, HERE)} "
                  f"({os.path.getsize(path) / 1024:.1f} KiB)")
    sys.exit(0)
