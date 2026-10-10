#!/usr/bin/env python3
"""
Generate Vera's iOS app icon — the SAME multicolor orb as the Mac app — into the
Xcode asset catalog (Assets.xcassets/AppIcon.appiconset).

Reuses the Mac icon's render_orb (macos/Vera/make-icon.py) so the two platforms
MATCH exactly. iOS icons can't be transparent, so the orb sits on the dark stage
it's designed to glow on. Run:  python3 make-appicon.py
(Brand rules: docs/BRAND.md.)
"""
import json
import os
import sys

from PIL import Image

# reuse the exact orb renderer from the Mac icon, so they're identical. The Mac
# file is hyphenated (make-icon.py), so load it by path.
import importlib.util as _ilu  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_MAC_ICON = os.path.join(_HERE, "..", "macos", "Vera", "make-icon.py")
_spec = _ilu.spec_from_file_location("mac_make_icon", _MAC_ICON)
_mac = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mac)
render_orb = _mac.render_orb

# iOS App Store / home-screen icon: a single 1024×1024, opaque. The dark stage is
# the same radial dark the orb glows on everywhere else (components/vera-orb-demo).
_BG_TOP = (21, 19, 31)       # #15131f
_BG_BOTTOM = (7, 6, 12)      # #07060c


def _radial_dark(size: int) -> Image.Image:
    """The dark circular stage, as a full-bleed radial gradient (opaque)."""
    bg = Image.new("RGB", (size, size))
    px = bg.load()
    cx = cy = size / 2
    maxd = (size / 2) * 1.42
    for y in range(size):
        for x in range(size):
            d = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / maxd)
            px[x, y] = tuple(
                round(_BG_TOP[i] + (_BG_BOTTOM[i] - _BG_TOP[i]) * d) for i in range(3)
            )
    return bg


def make_icon(size: int = 1024) -> Image.Image:
    bg = _radial_dark(size).convert("RGBA")
    # the orb, a touch larger than the Mac margin so it fills the rounded square well
    orb = render_orb(size)
    out = Image.alpha_composite(bg, orb)
    return out.convert("RGB")   # opaque — iOS rejects alpha in the app icon


def main():
    appiconset = os.path.join(_HERE, "Vera", "Assets.xcassets", "AppIcon.appiconset")
    os.makedirs(appiconset, exist_ok=True)
    # modern single-size iOS icon (Xcode 14+): one 1024 "universal" image
    make_icon(1024).save(os.path.join(appiconset, "icon-1024.png"))
    contents = {
        "images": [
            {"filename": "icon-1024.png", "idiom": "universal",
             "platform": "ios", "size": "1024x1024"}
        ],
        "info": {"author": "xcode", "version": 1},
    }
    with open(os.path.join(appiconset, "Contents.json"), "w") as f:
        json.dump(contents, f, indent=2)
    # the asset catalog also needs a top-level Contents.json
    xcassets = os.path.join(_HERE, "Vera", "Assets.xcassets")
    with open(os.path.join(xcassets, "Contents.json"), "w") as f:
        json.dump({"info": {"author": "xcode", "version": 1}}, f, indent=2)
    print(f"wrote {appiconset}/icon-1024.png + Contents.json")


if __name__ == "__main__":
    main()
