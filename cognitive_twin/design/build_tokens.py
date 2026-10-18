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


def main() -> None:
    css = build()
    OUT.write_text(css, encoding="utf-8")
    print(f"wrote {OUT} ({len(css)} bytes)")


if __name__ == "__main__":
    main()
