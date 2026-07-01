"""
brain.py — a graph view of how the twin thinks and learns.

Assembles a knowledge-graph snapshot of the twin's mind from REAL local state
(never invented): the cognitive faculties are CORE nodes; recurring topics the
twin has learned from your local history are LEARNED nodes; the active hours it
has noticed are RHYTHM nodes. Edges show how a faculty feeds a response, tagged
with provenance so the graph is honest about what's designed vs. observed —
inspired by graphify's EXTRACTED / INFERRED / AMBIGUOUS tags.

Everything here reads on-device state only (memory log, persona, mood, soul,
rhythms, activity). Nothing leaves the machine. Consumed by the /api/brain
endpoint and the macOS "Brain" view.

Node kinds:
  core     — a built-in faculty (memory, mood, persona, soul, rhythms, voice)
  learned  — a topic the twin learned from your actual usage
  rhythm   — an active hour it has observed
Edge kinds:
  wired    — a designed connection between faculties (always true)
  observed — a link grounded in real local data (topics ↔ memory, etc.)
  inferred — a plausible link the twin derives but doesn't directly observe
"""

from __future__ import annotations

from typing import Any


# The twin's faculties and the one-line role each plays in forming a response.
_FACULTIES = [
    ("memory", "Memory", "Recalls your recurring interests + recent asks (local log)."),
    ("persona", "Persona", "Who the twin is — the character you shaped."),
    ("soul", "Soul", "An evolving personality + reflections it has while you're away."),
    ("mood", "Mood", "Colors tone and how warm/measured the answer feels."),
    ("rhythms", "Rhythms", "Time-of-day + life-rhythm awareness (sleep/work)."),
    ("activity", "Activity", "Learns how you work by watching your active app (opt-in)."),
    ("voice", "Voice", "Speaks the answer in a loved one's cloned voice, on-device."),
    ("router", "Model router", "Picks the local model that reasons the reply."),
]

# How faculties feed one another to form a reply (designed wiring — always true).
_WIRING = [
    ("memory", "router"), ("persona", "router"), ("soul", "router"),
    ("mood", "router"), ("rhythms", "router"), ("activity", "memory"),
    ("router", "voice"), ("soul", "mood"), ("rhythms", "mood"),
]


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def snapshot() -> dict[str, Any]:
    """Build the brain graph from current local state."""
    from . import memory

    pats = _safe(memory.patterns, {"count": 0, "topics": [], "active_hours": []})

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # --- core faculties ---
    for fid, label, role in _FACULTIES:
        nodes.append({"id": fid, "label": label, "kind": "core", "role": role})

    for a, b in _WIRING:
        edges.append({"source": a, "target": b, "kind": "wired"})

    # --- learned topics (real, from your local history) ---
    topics = pats.get("topics", []) or []
    for i, topic in enumerate(topics):
        nid = f"topic:{topic}"
        # earlier topics are more frequent → a little heavier
        weight = round(1.0 - (i / max(1, len(topics))) * 0.5, 2)
        nodes.append({"id": nid, "label": topic, "kind": "learned", "weight": weight})
        edges.append({"source": nid, "target": "memory", "kind": "observed"})

    # --- observed active hours ---
    for h in (pats.get("active_hours", []) or []):
        nid = f"hour:{h}"
        nodes.append({"id": nid, "label": f"{h:02d}:00", "kind": "rhythm"})
        edges.append({"source": nid, "target": "rhythms", "kind": "observed"})

    # --- live faculty state (honest badges the UI can show) ---
    state: dict[str, Any] = {"memory_count": pats.get("count", 0)}
    try:
        from . import mood
        state["mood_on"] = _safe(mood.is_on, False)
        state["mood_style"] = _safe(mood.reflection_style, "")
    except Exception:
        pass
    try:
        from . import activity
        state["activity_enabled"] = _safe(activity.is_enabled, False)
        state["activity_observing"] = _safe(activity.observing, False)
        state["activity_private"] = _safe(activity.is_private, False)
    except Exception:
        pass
    try:
        from . import rhythms
        state["part_of_day"] = _safe(rhythms.part_of_day, "")
    except Exception:
        pass
    try:
        from . import persona
        state["persona"] = _safe(persona.status, "")
    except Exception:
        pass
    try:
        from . import soul
        refl = _safe(lambda: soul.pending_reflections(clear=False), [])
        state["reflections"] = len(refl)
    except Exception:
        pass

    return {
        "nodes": nodes,
        "edges": edges,
        "state": state,
        "legend": {
            "node_kinds": {"core": "built-in faculty", "learned": "learned from your usage", "rhythm": "observed active hour"},
            "edge_kinds": {"wired": "designed connection", "observed": "grounded in local data", "inferred": "derived, not directly observed"},
        },
    }


def thought_path(prompt: str) -> dict[str, Any]:
    """
    A best-effort 'how would this answer form?' — the ordered faculties a prompt
    is likely to route through. Heuristic + honest: it's the path, not a trace of
    an actual model run. The UI highlights these nodes/edges in order.
    """
    p = (prompt or "").lower()
    path = ["memory", "persona"]
    if any(w in p for w in ("feel", "sad", "miss", "love", "tired", "happy")):
        path.append("mood")
    if any(w in p for w in ("today", "now", "tonight", "morning", "sleep", "work")):
        path.append("rhythms")
    if any(w in p for w in ("what am i", "working on", "my app", "my project", "screen")):
        path.append("activity")
    path += ["router", "voice"]
    # de-dupe, preserve order
    seen, ordered = set(), []
    for n in path:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return {"prompt": prompt, "path": ordered}
