#!/usr/bin/env python3
"""build_tokens — generate tokens.css from tokens.json (the single source of truth).

The JSON is canonical and multi-platform (Python/Swift/JS all read it). This
script derives the CSS custom-property file the web surfaces serve, so a colour
is defined once and every renderer stays in sync.

    python3 -m cognitive_twin.design.build_tokens        # writes tokens.css next to tokens.json

© Ankur Sinha. Personal use.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = HERE / "tokens.json"
OUT = HERE / "tokens.css"
# BOTH apps read the SAME canonical tokens, emitted as a SwiftUI Color extension —
# one shared design system across the web, iOS, and macOS.
_ROOT = Path(__file__).resolve().parents[2]
SWIFT_OUT = _ROOT / "ios" / "Vera" / "Sources" / "VeraTokens.swift"
SWIFT_OUT_MAC = _ROOT / "macos" / "Vera" / "Sources" / "Vera" / "VeraTokens.swift"

# camelCase token name → kebab CSS var name (accentInk → --accent-ink).
def _kebab(name: str) -> str:
    out = []
    for ch in name:
        if ch.isupper():
            out.append("-" + ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def build() -> str:
    t = json.loads(TOKENS.read_text(encoding="utf-8"))
    color = t["color"]
    shadow = t["shadow"]

    def scheme(mode: str) -> str:
        lines = []
        for name, pair in color.items():
            lines.append(f"  --{_kebab(name)}: {pair[mode]};")
        for name, pair in shadow.items():
            lines.append(f"  --shadow-{_kebab(name)}: {pair[mode]};")
        return "\n".join(lines)

    # Non-theme scalars (same in both modes).
    scalar = []
    for k, v in t["radius"].items():
        scalar.append(f"  --radius-{k}: {v};")
    for k, v in t["space"].items():
        scalar.append(f"  --space-{k}: {v};")
    for k, v in t["toggle"].items():
        scalar.append(f"  --toggle-{_kebab(k)}: {v};")
    scalar.append(f"  --font-family: {t['font']['family']};")
    scalar.append(f"  --font-size: {t['font']['size']};")
    scalar.append(f"  --line-height: {t['font']['lineHeight']};")
    scalar_block = "\n".join(scalar)

    return (
        "/* GENERATED from tokens.json by design/build_tokens.py — do not edit by hand. */\n"
        ":root{\n" + scalar_block + "\n" + scheme("light") + "\n}\n"
        "@media (prefers-color-scheme: dark){:root{\n" + scheme("dark") + "\n}}\n"
    )


def _hex_to_swift(h: str) -> str:
    """'#3ecf8e' → a SwiftUI Color(red:…, green:…, blue:…) with 0–1 components."""
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"Color(red: {r/255:.3f}, green: {g/255:.3f}, blue: {b/255:.3f})"


def build_swift() -> str:
    t = json.loads(TOKENS.read_text(encoding="utf-8"))
    color = t["color"]
    # Dynamic colours: light value by default, dark value via UITraitCollection so
    # a single Color adapts to the system appearance — same as the CSS @media.
    lines = []
    for name, pair in color.items():
        light = _hex_to_swift(pair["light"])
        dark = _hex_to_swift(pair["dark"])
        lines.append(
            f"    /// {name} — from tokens.json (light/dark).\n"
            f"    static let {name} = dynamic(light: {light}, dark: {dark})"
        )
    body = "\n".join(lines)
    return (
        "// GENERATED from cognitive_twin/design/tokens.json by build_tokens.py — do not edit by hand.\n"
        "// The iOS app's half of Vera's one shared design system (Tailscale-quality).\n"
        "import SwiftUI\n"
        "#if canImport(UIKit)\nimport UIKit\n#endif\n\n"
        "enum VeraTokens {\n"
        "    /// A Color that resolves light/dark from the system appearance.\n"
        "    static func dynamic(light: Color, dark: Color) -> Color {\n"
        "        #if canImport(UIKit)\n"
        "        return Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })\n"
        "        #else\n"
        "        return light\n"
        "        #endif\n"
        "    }\n\n"
        f"{body}\n"
        "}\n"
    )


def main() -> None:
    css = build()
    OUT.write_text(css, encoding="utf-8")
    print(f"wrote {OUT} ({len(css)} bytes)")
    swift = build_swift()
    for out in (SWIFT_OUT, SWIFT_OUT_MAC):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(swift, encoding="utf-8")
        print(f"wrote {out} ({len(swift)} bytes)")


if __name__ == "__main__":
    main()
