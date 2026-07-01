#!/usr/bin/env python3
"""
Generate Anita's app icon — her multicolor Siri orb — at all macOS sizes, and
package it into AppIcon.icns. Run: python3 make-icon.py

Mirrors the SwiftUI SiriOrb: a dark sphere with soft, swirling color blobs
(pink/purple/blue/cyan/orange), a bright core, a glassy highlight, and a glow.
"""
import math
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFilter

BLOBS = [
    (255, 69, 140),   # pink
    (158, 77, 255),   # purple
    (51, 133, 255),   # blue
    (46, 217, 242),   # cyan
    (255, 158, 51),   # orange
]


def render_orb(size: int) -> Image.Image:
    # supersample for smoothness
    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx, cy = S / 2, S / 2
    r = S * 0.42  # orb radius (leaves margin for glow)

    # --- glow ---
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([cx - r * 1.25, cy - r * 1.25, cx + r * 1.25, cy + r * 1.25],
               fill=(120, 90, 255, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.06))
    img = Image.alpha_composite(img, glow)

    # --- orb base (dark, so colors glow) ---
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bd = ImageDraw.Draw(base)
    bd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(14, 16, 24, 255))
    img = Image.alpha_composite(img, base)

    # --- swirling color blobs (additive) ---
    blobs = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for i, (cr, cg, cb) in enumerate(BLOBS):
        a = i * (2 * math.pi / len(BLOBS)) + 0.5
        orbit = r * 0.32
        bx = cx + math.cos(a) * orbit
        by = cy + math.sin(a) * orbit
        br = r * 0.62
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse([bx - br, by - br, bx + br, by + br], fill=(cr, cg, cb, 200))
        layer = layer.filter(ImageFilter.GaussianBlur(S * 0.05))
        # additive blend
        blobs = Image.alpha_composite(blobs, layer)

    # clip blobs to the orb circle
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    blobs.putalpha(Image.composite(blobs.getchannel("A"), Image.new("L", (S, S), 0), mask))
    img = Image.alpha_composite(img, blobs)

    # --- bright core ---
    core = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cd = ImageDraw.Draw(core)
    cr_ = r * 0.30
    cd.ellipse([cx - cr_, cy - cr_, cx + cr_, cy + cr_], fill=(255, 255, 255, 180))
    core = core.filter(ImageFilter.GaussianBlur(S * 0.04))
    img = Image.alpha_composite(img, core)

    # --- glassy highlight (top-left) ---
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    hx, hy, hr = cx - r * 0.28, cy - r * 0.34, r * 0.42
    hd.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=(255, 255, 255, 110))
    hl = hl.filter(ImageFilter.GaussianBlur(S * 0.03))
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (S, S), 0), mask))
    img = Image.alpha_composite(img, hl)

    return img.resize((size, size), Image.LANCZOS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_icns = os.path.join(here, "AppIcon.icns")

    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "AppIcon.iconset")
        os.makedirs(iconset)
        # macOS iconset sizes (1x + 2x)
        specs = [16, 32, 64, 128, 256, 512, 1024]
        for s in specs:
            render_orb(s).save(os.path.join(iconset, f"icon_{s}x{s}.png"))
        # 2x aliases the iconutil naming expects
        pairs = [(16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
                 (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
                 (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x")]
        for s, name in pairs:
            render_orb(s).save(os.path.join(iconset, f"icon_{name}.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out_icns], check=True)
    print(f"wrote {out_icns}")


if __name__ == "__main__":
    main()
