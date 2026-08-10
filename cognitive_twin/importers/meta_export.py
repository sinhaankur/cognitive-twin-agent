"""
meta_export — parse your Meta "Download Your Information" export into Vera.

Facebook & Instagram can't be live-connected privately (Meta removed the APIs;
scraping = a ban). The private path is *your* official export: request it in
Accounts Center → "Download your information" → **JSON** format, download the zip,
unzip it, and point Vera at the folder. This reads those local JSON files, scores
the sentiment of what YOU wrote on-device, and folds it into the sealed ``social``
index. Nothing is scraped; nothing is uploaded.

Handles the common export shapes (Meta renames paths over time, so we glob by
content, not exact path):
  • Facebook posts        — ``your_posts*.json`` / ``posts/…`` with ``data[].post``
  • Facebook comments     — ``comments*.json`` with ``author`` + ``data[].comment``
  • Instagram posts       — ``content/posts_1.json`` (media + caption)
  • Instagram comments    — ``comments/post_comments*.json``
  • Reactions / likes     — ``likes_and_reactions*`` / ``liked_posts.json``
  • Messages (metadata)   — ``messages/**/message_*.json`` (we keep counts + your
                            own message text for sentiment, not others' content)

Mojibake fix: Meta double-encodes UTF-8 in JSON; we repair it on read.

    python3 -m cognitive_twin.importers.meta_export <export-folder> [--dry-run]

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ..social import Activity, import_activities, is_enabled
from .sentiment import score as _sentiment


# ── Meta's UTF-8 mojibake repair ───────────────────────────────────────────────
def _fix(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _ts(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── extractors per file kind (sniffed by content, not path) ────────────────────
def _fb_posts(data: Any) -> Iterator[Activity]:
    rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ts = _ts(row.get("timestamp"))
        if ts is None:
            continue
        text = ""
        for d in row.get("data", []) or []:
            if isinstance(d, dict) and "post" in d:
                text = _fix(d["post"])
        if not text:
            text = _fix(row.get("title", ""))
        yield Activity(platform="facebook", kind="post", ts=ts, text=text)


def _fb_comments(data: Any) -> Iterator[Activity]:
    rows = (data.get("comments_v2") or data.get("comments") or data.get("data", [])
            ) if isinstance(data, dict) else data
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ts = _ts(row.get("timestamp"))
        if ts is None:
            continue
        text = ""
        target = _fix(row.get("title", ""))
        for d in row.get("data", []) or []:
            if isinstance(d, dict) and "comment" in d:
                c = d["comment"]
                text = _fix(c.get("comment", "")) if isinstance(c, dict) else _fix(c)
        yield Activity(platform="facebook", kind="comment", ts=ts, text=text, target=target)


def _ig_posts(data: Any) -> Iterator[Activity]:
    rows = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        # IG post: media[].creation_timestamp + title/caption
        media = row.get("media", [])
        ts = _ts(row.get("creation_timestamp"))
        text = _fix(row.get("title", ""))
        if media and isinstance(media, list) and isinstance(media[0], dict):
            ts = ts or _ts(media[0].get("creation_timestamp"))
            text = text or _fix(media[0].get("title", ""))
        if ts is None:
            continue
        yield Activity(platform="instagram", kind="post", ts=ts, text=text)


def _reactions(data: Any, platform: str) -> Iterator[Activity]:
    rows = (data.get("reactions_v2") or data.get("likes_media_likes")
            or data.get("data", [])) if isinstance(data, dict) else data
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        ts = _ts(row.get("timestamp"))
        title = _fix(row.get("title", ""))
        # IG likes shape: {"title":..., "string_list_data":[{"timestamp":...}]}
        if ts is None:
            sld = row.get("string_list_data") or []
            if sld and isinstance(sld[0], dict):
                ts = _ts(sld[0].get("timestamp"))
                title = title or _fix(sld[0].get("value", ""))
        if ts is None:
            continue
        yield Activity(platform=platform, kind="reaction", ts=ts, target=title)


def _messages(path: Path, self_name: str | None) -> Iterator[Activity]:
    data = _load(path)
    if not isinstance(data, dict):
        return
    thread = _fix(data.get("title", "")) or path.parent.name
    for m in data.get("messages", []) or []:
        if not isinstance(m, dict):
            continue
        ts = _ts(m.get("timestamp_ms"))
        if ts is None:
            continue
        ts = ts / 1000.0
        sender = _fix(m.get("sender_name", ""))
        # Only keep YOUR message text for sentiment; others' text stays a count.
        mine = self_name is not None and sender == self_name
        yield Activity(platform="facebook", kind="message", ts=ts,
                       text=_fix(m.get("content", "")) if mine else "",
                       target=thread, meta={"sender": sender, "mine": mine})


# ── walk the export folder ─────────────────────────────────────────────────────
def _self_name(root: Path) -> str | None:
    """Best-effort: read the account owner's name from profile info if present."""
    for p in root.rglob("*.json"):
        name = p.name.lower()
        if "profile_information" in name or "personal_information" in name:
            data = _load(p)
            try:
                pv = data["profile_v2"] if "profile_v2" in data else data.get("profile_user", [{}])[0]
                nm = pv.get("name", {})
                return _fix(nm.get("full_name") if isinstance(nm, dict) else nm)
            except Exception:
                continue
    return None


def parse(folder: str | Path) -> list[Activity]:
    root = Path(folder).expanduser()
    if not root.exists():
        return []
    self_name = _self_name(root)
    acts: list[Activity] = []

    for p in root.rglob("*.json"):
        name = p.name.lower()
        rel = str(p).lower()
        try:
            if "message_" in name and "messages" in rel:
                acts.extend(_messages(p, self_name))
                continue
            data = _load(p)
            if data is None:
                continue
            if "your_posts" in name or ("posts" in rel and "post" in name and "instagram" not in rel):
                acts.extend(_fb_posts(data))
            elif "comment" in name and "instagram" not in rel:
                acts.extend(_fb_comments(data))
            elif "posts_1" in name or ("instagram" in rel and "post" in name):
                acts.extend(_ig_posts(data))
            elif "like" in name or "reaction" in name:
                platform = "instagram" if "instagram" in rel else "facebook"
                acts.extend(_reactions(data, platform))
        except Exception:
            continue

    # score sentiment on-device for anything with your own words
    for a in acts:
        if a.text:
            a.sentiment = _sentiment(a.text)
    acts.sort(key=lambda a: a.ts)
    return acts


def import_from(folder: str | Path) -> dict[str, Any]:
    if not is_enabled():
        return {"imported": 0, "parsed": 0,
                "note": "social tracking is off — run `social enable` first."}
    acts = parse(folder)
    n = import_activities(acts)
    return {"imported": n, "parsed": len(acts)}


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m cognitive_twin.importers.meta_export <export-folder> [--dry-run]")
        return 2
    folder = argv[0]
    if "--dry-run" in argv:
        acts = parse(folder)
        from collections import Counter
        by = Counter((a.platform, a.kind) for a in acts)
        print(f"Parsed {len(acts)} activities from {folder} (dry run):")
        for (plat, kind), n in by.most_common():
            print(f"  {plat} {kind}: {n}")
        return 0
    r = import_from(folder)
    if r.get("note"):
        print(r["note"]); return 1
    print(f"✓ Imported {r['imported']} social activities (parsed {r['parsed']}) "
          f"into the sealed index.")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
