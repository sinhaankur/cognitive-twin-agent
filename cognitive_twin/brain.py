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
    ("shadow", "Shadow", "Follows your day — tasks you mention, tracked to done (local ledger)."),
    ("voice", "Voice", "Speaks the answer in a loved one's cloned voice, on-device."),
    ("router", "Model router", "Picks the local model that reasons the reply."),
]

# How faculties feed one another to form a reply (designed wiring — always true).
_WIRING = [
    ("memory", "router"), ("persona", "router"), ("soul", "router"),
    ("mood", "router"), ("rhythms", "router"), ("activity", "memory"),
    ("memory", "shadow"), ("shadow", "router"),
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
    try:
        from . import shadow
        state["open_tasks"] = len(_safe(shadow.open_tasks, []))
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


def landscape(limit: int = 60) -> dict[str, Any]:
    """A 'landscape of thoughts' layout — memories placed in 2D so related ones
    (sharing content words) sit near each other, and clusters read as terrain.

    This is the honest, zero-dependency stand-in for the t-SNE map in
    tmlr-group/landscape-of-thoughts: instead of embedding reasoning traces with
    ML, we lay out *real* local memories by term-overlap using a tiny iterative
    force relaxation (attract when they share words, gently repel otherwise).
    Points carry a 'heat' the UI shades into density so clusters look like
    valleys. No numpy, no model — a few hundred cheap iterations in pure Python.

    Returns points in a normalized [0,1] x [0,1] space plus the shared terms per
    point, so the UI can label clusters. Everything derives from local memory.
    """
    from . import memory
    import math
    import random

    from . import mem_types

    es = _safe(lambda: memory.entries(limit=limit), []) or []
    # one point per memory, keyed by its content-word set
    pts: list[dict[str, Any]] = []
    for e in es:
        terms = memory._terms(e.get("prompt", "")) | memory._terms(e.get("gist", ""))
        if not terms:
            continue
        label = (e.get("prompt", "") or "").strip()
        # type: stored on new memories; classify on the fly for older ones
        mtype = e.get("type") or _safe(lambda: mem_types.classify(label), "knowledge")
        pts.append({
            "terms": terms,
            "label": (label[:40] + "…") if len(label) > 41 else label,
            "ts": (e.get("ts", "") or "")[:10],
            "type": mtype,
            "entry": e,
        })
    n = len(pts)
    if n == 0:
        return {"points": [], "bounds": [0, 0, 1, 1]}

    # similarity = Jaccard overlap of term sets (0..1)
    def sim(a: int, b: int) -> float:
        ta, tb = pts[a]["terms"], pts[b]["terms"]
        if not ta or not tb:
            return 0.0
        inter = len(ta & tb)
        return inter / len(ta | tb) if inter else 0.0

    rnd = random.Random(1234)  # deterministic layout for a given memory set
    xs = [rnd.random() for _ in range(n)]
    ys = [rnd.random() for _ in range(n)]

    # force relaxation: every pair springs toward a target gap set by how much
    # they share — similar → close (~0.12), unrelated → a moderate spread (~0.6,
    # not the far corner, so clusters stay legible). Similar pairs pull harder so
    # topics visibly gather. ~250 iters settles tens of points cheaply.
    for _ in range(250):
        fx = [0.0] * n
        fy = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                dx = xs[i] - xs[j]
                dy = ys[i] - ys[j]
                d = math.hypot(dx, dy) or 1e-4
                s = sim(i, j)
                target = 0.6 - 0.48 * s               # 0.6 apart … 0.12 when identical
                stiffness = 0.14 if s > 0 else 0.05   # shared-word pairs pull harder
                force = (d - target) * stiffness
                ux, uy = dx / d, dy / d
                fx[i] -= ux * force; fy[i] -= uy * force
                fx[j] += ux * force; fy[j] += uy * force
        for i in range(n):
            xs[i] += max(-0.04, min(0.04, fx[i]))
            ys[i] += max(-0.04, min(0.04, fy[i]))

    # normalize into [0,1]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    sx = (maxx - minx) or 1.0
    sy = (maxy - miny) or 1.0
    strengths = _safe(memory._strengths, {})
    points = []
    for i, p in enumerate(pts):
        # heat = how clustered this point is (sum of similarities to others)
        # + reconsolidation: memories she actually uses in thought grow hotter,
        # which the Mind renders as drifting closer to her core
        heat = sum(sim(i, j) for j in range(n) if j != i)
        heat += 0.35 * math.log1p(strengths.get(memory._skey(p["entry"]), 0))
        points.append({
            "x": round((xs[i] - minx) / sx, 4),
            "y": round((ys[i] - miny) / sy, 4),
            "label": p["label"],
            "ts": p["ts"],
            "type": p["type"],
            "color": mem_types.color(p["type"]),
            "heat": round(heat, 3),
            "terms": sorted(p["terms"])[:5],
        })
    # links = related memory pairs (shared words), so the universe view can draw
    # the filaments that show *how* thoughts connect. Cap per-node degree so the
    # web stays legible; keep each node's strongest few ties.
    links: list[dict[str, Any]] = []
    for i in range(n):
        sims = sorted(((sim(i, j), j) for j in range(n) if j != i), reverse=True)
        for s, j in sims[:3]:
            if s >= 0.12 and i < j:      # threshold + de-dupe (i<j)
                links.append({"a": i, "b": j, "w": round(s, 3)})

    # per-type tallies so the UI can show a legend / region sizes
    type_counts: dict[str, int] = {}
    for p in points:
        type_counts[p["type"]] = type_counts.get(p["type"], 0) + 1
    return {
        "points": points, "links": links, "bounds": [0, 0, 1, 1], "count": n,
        "types": {t: {"count": type_counts.get(t, 0),
                      "color": mem_types.color(t), "label": mem_types.label(t)}
                  for t in mem_types.TYPES},
    }
