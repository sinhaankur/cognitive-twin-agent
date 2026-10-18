# Vera design tokens — one visual system, every surface

`tokens.json` is the **single source of truth** for Vera's look (Tailscale-quality:
one green accent, flat cards, system/Inter font, light + dark). Every renderer reads
these values instead of hand-copying a hex — that's how the web dashboard, iOS,
Windows, Linux, and the BuildingLink booker stay visually identical.

## Files
- `tokens.json` — canonical tokens (colours light/dark, radius, spacing, font, toggle geometry). Edit here.
- `build_tokens.py` — generates `tokens.css` from the JSON. Run after any edit.
- `tokens.css` — **generated** CSS custom properties (don't edit by hand). Served by the web surfaces at `/tokens.css`.

## Regenerate
```
python3 -m cognitive_twin.design.build_tokens
```

## Who consumes it
- **Vera web settings** (`dashboard.py` → `/settings`) links `/tokens.css`.
- **BuildingLink booker dashboard** (`~/Documents/buildinglink-booker/public/index.html`) links a synced copy of `tokens.css`. Re-sync after regenerating:
  `cp cognitive_twin/design/tokens.css ~/Documents/buildinglink-booker/public/tokens.css`
- **iOS / Windows / Linux** (planned) read the same `tokens.json` to build native styles.
