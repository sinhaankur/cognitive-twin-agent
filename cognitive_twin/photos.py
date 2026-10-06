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


def learn_places(places: list[dict[str, Any]]) -> dict[str, int]:
    """Store PLACES you've been (from photo location metadata) as memories, so
    Vera knows where you've travelled. Metadata only, on-device, dedup-safe.
    Each record: a place name, how many photos, and the date span of the visit."""
    from . import memory
    known = {e.get("prompt") for e in memory.entries() if e.get("source") == "photos-places"}
    learned = skipped = 0
    for p in places or []:
        name = (p.get("region") or p.get("place") or "").strip()
        if not name:
            continue
        prompt = f"a place you've been: {name}"
        if prompt in known:
            skipped += 1
            continue
        photos_n = p.get("photos")
        first, last = p.get("first"), p.get("last")
        span = (f"{first} → {last}" if first and last and first != last
                else (first or last or ""))
        gist = "from your photos' location metadata (opt-in)"
        if photos_n:
            gist += f": {photos_n} photos"
        if span:
            gist += f", {span}"
        memory.record(prompt, gist, source="photos-places")
        known.add(prompt)
        learned += 1
    return {"places_learned": learned, "places_skipped": skipped}


def learn_moments(moments: list[dict[str, Any]]) -> dict[str, int]:
    """Store LIFE MOMENTS (recent outings/sessions from photo metadata) as memories
    so Vera can recall your days — 'a full Saturday in Pune, lots of photos'. Each
    moment: day, weekday, part of day, photo count, span, and place if known.
    Metadata only, on-device, dedup-safe by day+part."""
    from . import memory
    known = {e.get("prompt") for e in memory.entries() if e.get("source") == "photos-moments"}
    learned = skipped = 0
    for m in moments or []:
        day = (m.get("day") or "").strip()
        if not day:
            continue
        weekday = m.get("weekday") or ""
        part = m.get("part") or ""
        place = m.get("place")
        n = m.get("photos")
        span = m.get("spanHours")
        where = f" in {place}" if place else ""
        prompt = f"a moment in your life: {weekday} {part}{where} ({day})"
        if prompt in known:
            skipped += 1
            continue
        bits = []
        if n:
            bits.append(f"{n} photos")
        if isinstance(span, int) and span >= 1:
            bits.append(f"over about {span}h")
        gist = "from your photos (opt-in, metadata only)"
        if bits:
            gist += " — " + ", ".join(bits)
        memory.record(prompt, gist, source="photos-moments")
        known.add(prompt)
        learned += 1
    return {"moments_learned": learned, "moments_skipped": skipped}


def life_recap(days: int = 7) -> str:
    """A short, human recap of your recent life from what she's learned — moments,
    places, events in the last `days`. For 'what did I do this weekend / lately'.
    Reads only the sealed photo-memories; returns '' if she hasn't learned any."""
    from . import memory
    import datetime as _dt
    cutoff = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
    moments, places = [], []
    for e in memory.entries():
        src = e.get("source")
        prompt = (e.get("prompt") or "")
        ts = (e.get("ts") or "")[:10]
        if src == "photos-moments" and ts >= cutoff:
            moments.append(prompt.replace("a moment in your life: ", ""))
        elif src == "photos-places" and ts >= cutoff:
            places.append(prompt.replace("a place you've been: ", ""))
    if not moments and not places:
        return ""
    parts = []
    if moments:
        parts.append("Lately: " + "; ".join(moments[:5]) + ".")
    if places:
        uniq = list(dict.fromkeys(places))
        parts.append("Places: " + ", ".join(uniq[:5]) + ".")
    return " ".join(parts)
