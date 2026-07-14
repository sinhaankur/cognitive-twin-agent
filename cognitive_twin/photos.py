"""
photos.py — life events she learned from your Photos library (opt-in).

Fed ONLY by the Mac app's "Let her read my Photos" switch (PhotosReader.swift).
Nothing arrives here unless the user flipped it on and macOS granted access on
top. Even then the app sends METADATA-derived events only — album titles and
dates, never pixels: "the 'Mom 60th' album is a birthday around 2019-06-03",
"June 3rd fills with photos every year". Each becomes an ordinary memory
(source "photos"), dedup-safe so rescans never double-learn.

Honesty rules: an event is stored with its provenance in the text ("from my
Photos"), annual spikes are stored as open questions ("maybe a birthday or
anniversary") because the metadata doesn't say whose — she can ask, not assume.
"""

from __future__ import annotations

from typing import Any

_KIND_LINE = {
    "birthday":     "a birthday",
    "anniversary":  "an anniversary",
    "wedding":      "a wedding",
    "remembrance":  "a remembrance — someone being mourned or missed",
    "family event": "a family event",
    "trip":         "a trip together",
}


def _prompt_for(ev: dict[str, Any]) -> str | None:
    """The deterministic memory text for one event — also the dedupe key."""
    kind = ev.get("kind") or ""
    if kind == "annual":
        md, years = ev.get("monthday"), ev.get("years") or []
        if not md or len(years) < 2:
            return None
        ys = ", ".join(str(y) for y in years[:6])
        return (f"From my Photos: every year around {md} the library fills with "
                f"photos ({ys}) — maybe a birthday or anniversary; worth asking whose.")
    title, date = (ev.get("title") or "").strip(), ev.get("date") or ""
    if not title or kind not in _KIND_LINE:
        return None
    when = f" around {date}" if date else ""
    return f"From my Photos: the album '{title}' — {_KIND_LINE[kind]}{when}."


def learn(events: list[dict[str, Any]]) -> dict[str, int]:
    """Store new events as memories; skip anything already learned."""
    from . import memory
    known = {e.get("prompt") for e in memory.entries() if e.get("source") == "photos"}
    learned = skipped = 0
    for ev in events or []:
        prompt = _prompt_for(ev)
        if not prompt:
            continue
        if prompt in known:
            skipped += 1
            continue
        count = ev.get("count")
        gist = (f"learned from the Photos library (opt-in switch): "
                f"{count} photos" if count else "learned from the Photos library (opt-in switch)")
        until = ev.get("until")
        if until and until != ev.get("date"):
            gist += f", {ev.get('date')} → {until}"
        memory.record(prompt, gist, source="photos")
        known.add(prompt)
        learned += 1
    return {"learned": learned, "skipped": skipped}
