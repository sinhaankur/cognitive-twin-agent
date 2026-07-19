# Vera — brand guide

One page. Everything a surface (app, README, icon, store listing) needs to look
and sound like Vera — pulled from what the code already does, not invented.

## The name

**Vera** — Latin *verus*: **true, faithful**. The name is the promise:
honest data, local-first, nothing leaves the device unless you allow it.

**The rule:** *Vera is the product. Anita is the default persona.*

- Product surfaces (app name, window titles, README, icon) say **Vera**.
- The persona — who she *is* to you — defaults to **Anita** and is yours to
  change. Persona names never appear as the product name.
- Bundle identifier `com.sinhaankur.anita` is **frozen** on both platforms:
  changing it would reset the mic/speech/camera permissions users already
  granted. It is an internal ID, not a brand surface.

## Tagline

> Your faithful presence — private, on-device.

## The mark

The **orb**: a dark glass sphere with five swirling color blobs, a bright core,
and a soft glow. It is the app icon, the floating presence on screen, and the
logo. One mark, everywhere.

- Generated: `macos/Vera/make-icon.py` (icns), `SiriOrb.swift` (live view)
- Wordmark: `docs/vera-logo.svg` (orb + "Vera", for dark backgrounds)

## Palette

The five blob colors and the base, exactly as they appear in
`SiriOrb.swift` and `make-icon.py`:

| Color  | Hex       | RGB           |
|--------|-----------|---------------|
| Pink   | `#FF458C` | 255, 69, 140  |
| Purple | `#9E4DFF` | 158, 77, 255  |
| Blue   | `#3385FF` | 51, 133, 255  |
| Cyan   | `#2ED9F2` | 46, 217, 242  |
| Orange | `#FF9E33` | 255, 158, 51  |
| Base   | `#0E1018` | 14, 16, 24    |

No single color owns the brand — the *mix* does. New surfaces pick from this
palette; don't add colors.

## Voice

Plain, warm, honest. She says what she measured and where it came from
(provenance), and never claims a sense that isn't switched on. Broken states
never animate. Intellectual over cute; short over long.

Words we use: *presence, faithful, on-device, private, yours.*
Words we don't: *cloud, platform, assistant ecosystem, AI-powered.*
