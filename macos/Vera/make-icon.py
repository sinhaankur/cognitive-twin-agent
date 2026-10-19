#!/usr/bin/env python3
"""
Generate Vera's app icon — her DOTTED FIELD in her warm gold identity — at all
macOS sizes, and package it into AppIcon.icns. Run: python3 make-icon.py
(Palette and brand rules: docs/BRAND.md.)

This mirrors the app's live DottedOrb (and the website's dotted orb): a
Fibonacci-sphere of points, depth-shaded (near dots bigger/brighter), tinted
gold, over a soft dark ground with a warm bloom. It replaces the old
iridescent-blob icon so the Dock/Finder/Spotlight icon looks like who she is now.
"""
import math
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFilter

# Vera's gold — the identity accent (tokens.json accent.dark #d6a95f, the new
# natural amber). Keep this in lockstep with tokens.json so the icon and the app
# are the exact same colour.
GOLD = (214, 169, 95)          # natural amber, the dot colour
GOLD_BLOOM = (214, 169, 95)    # bloom behind the sphere
# Dark ground so the gold glows (a near-black with a faint warm cast). Kept
# deep so the gold reads as light, not paint — richer than a flat brown.
GROUND_TOP = (26, 22, 16)
GROUND_BOTTOM = (6, 5, 4)

N_POINTS = 420                  # denser than the live orb — an icon can afford it


def _fib_sphere(n):
    pts = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - (i / (n - 1)) * 2
        r = math.sqrt(max(0.0, 1 - y * y))
        t = golden * i
        pts.append((math.cos(t) * r, y, math.sin(t) * r))
    return pts


_POINTS = _fib_sphere(N_POINTS)


def render_orb(size: int) -> Image.Image:
    # supersample for smoothness
    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx, cy = S / 2, S / 2

    # --- rounded-square dark ground (macOS app-icon shape) ---
    ground = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(ground)
    inset = S * 0.06
    radius = S * 0.225                     # macOS "squircle"-ish corner
    # vertical gradient fill
    grad = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for yy in range(S):
        f = yy / S
        r = int(GROUND_TOP[0] + (GROUND_BOTTOM[0] - GROUND_TOP[0]) * f)
        g = int(GROUND_TOP[1] + (GROUND_BOTTOM[1] - GROUND_TOP[1]) * f)
        b = int(GROUND_TOP[2] + (GROUND_BOTTOM[2] - GROUND_TOP[2]) * f)
        ImageDraw.Draw(grad).line([(0, yy), (S, yy)], fill=(r, g, b, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [inset, inset, S - inset, S - inset], radius=radius, fill=255)
    ground = Image.composite(grad, ground, mask)
    img = Image.alpha_composite(img, ground)

    # --- warm gold bloom behind the sphere ---
    R = S * 0.30                           # sphere projected radius
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [cx - R * 1.6, cy - R * 1.6, cx + R * 1.6, cy + R * 1.6],
        fill=(*GOLD_BLOOM, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.05))
    glow = Image.composite(glow, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask)
    img = Image.alpha_composite(img, glow)

    # --- the dotted field (gold points on a Fibonacci sphere) ---
    dots = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    # a gentle fixed pose so the sphere reads 3D (rotate Y a little, tilt X).
    ry, rx = 0.6, 0.34
    cosY, sinY = math.cos(ry), math.sin(ry)
    cosX, sinX = math.cos(rx), math.sin(rx)
    # paint back-to-front so near dots sit over far dots
    projected = []
    for (x, y, z) in _POINTS:
        x1 = x * cosY - z * sinY
        z1 = x * sinY + z * cosY
        y1 = y * cosX - z1 * sinX
        z2 = y * sinX + z1 * cosX
        projected.append((x1, y1, z2))
    projected.sort(key=lambda p: p[2])     # far first
    for (x1, y1, z2) in projected:
        px = cx + x1 * R
        py = cy + y1 * R
        depth = (z2 + 1) / 2               # 0 back → 1 front
        dot_r = S * (0.004 + depth * 0.012)
        alpha = int(255 * (0.14 + depth * 0.82))
        dd.ellipse([px - dot_r, py - dot_r, px + dot_r, py + dot_r],
                   fill=(*GOLD, alpha))
    img = Image.alpha_composite(img, dots)

    return img.resize((size, size), Image.LANCZOS)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_icns = os.path.join(here, "AppIcon.icns")

    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "AppIcon.iconset")
        os.makedirs(iconset)
        specs = [16, 32, 64, 128, 256, 512, 1024]
        for s in specs:
            render_orb(s).save(os.path.join(iconset, f"icon_{s}x{s}.png"))
        pairs = [(16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
                 (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
                 (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x")]
        for s, name in pairs:
            render_orb(s).save(os.path.join(iconset, f"icon_{name}.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out_icns], check=True)
    print(f"wrote {out_icns}")


if __name__ == "__main__":
    main()
