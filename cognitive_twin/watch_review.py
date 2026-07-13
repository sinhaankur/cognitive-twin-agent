"""
Watch review — "here's what happened while you were away."

Reads the notes that watch.py logged (read-only) and turns them into a short
digest for when you come back: how long the session ran, which apps you spent
time in, and — if a local twin is reachable — a brief "what I noticed / what
you might pick up next" summary. If no model is up, it still gives you the
factual rollup, entirely offline.

Read-only: this only reads ~/.cognitive-twin/watch-notes.md (or CTWIN_WATCH_FILE)
and prints. It changes nothing and uploads nothing.

CLI:
    python3 -m cognitive_twin.watch_review [--since HH:MM] [--no-llm] [--raw]
      --since   only consider observations at/after this time today (e.g. 14:30)
      --no-llm  skip the twin digest; print the factual rollup only
      --raw     print the parsed observations, not the digest
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Matches an observation header written by watch._append_note, e.g.
#   ### 2026-07-13 09:14:02 — Code  _(via ocr)_
_OBS = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+—\s+(.*?)\s+_\(via (.*?)\)_\s*$"
)


def _notes_file() -> Path:
    p = os.environ.get("CTWIN_WATCH_FILE")
    if p:
        return Path(p)
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    return root / "watch-notes.md"


@dataclass
class Observation:
    ts: str
    app: str
    strategy: str
    body: str = ""            # the excerpt lines (twin note + '> …' quote), joined


@dataclass
class Review:
    observations: list[Observation] = field(default_factory=list)

    @property
    def span(self) -> str:
        if not self.observations:
            return ""
        a, b = self.observations[0].ts, self.observations[-1].ts
        try:
            ta = datetime.fromisoformat(a); tb = datetime.fromisoformat(b)
            mins = round((tb - ta).total_seconds() / 60)
            return f"{a} → {b} (~{mins} min)"
        except ValueError:
            return f"{a} → {b}"

    @property
    def apps(self) -> list[tuple[str, int]]:
        c = Counter(o.app for o in self.observations if o.app)
        return c.most_common()

    @property
    def time_in_app(self) -> list[tuple[str, float]]:
        """Estimated minutes spent per app, from the gap between consecutive
        observations (each observation 'holds' until the next one). More honest
        than raw counts — a single long stint in one app reads as time, not a
        tally. Sorted by time descending."""
        obs = self.observations
        if not obs:
            return []
        mins: Counter[str] = Counter()
        for i, o in enumerate(obs):
            t0 = _safe_dt(o.ts)
            if not t0 or not o.app:
                continue
            t1 = _safe_dt(obs[i + 1].ts) if i + 1 < len(obs) else t0
            gap = (t1 - t0).total_seconds() / 60 if t1 else 0.0
            # clamp per-interval gap so one idle jump doesn't dominate
            mins[o.app] += max(0.0, min(gap, 15.0)) or 0.25
        return sorted(mins.items(), key=lambda kv: kv[1], reverse=True)


def parse(text: str) -> Review:
    """Parse a watch-notes file body into a Review of observations."""
    obs: list[Observation] = []
    cur: Observation | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = _OBS.match(line)
        if m:
            if cur is not None:
                cur.body = "\n".join(buf).strip()
                obs.append(cur)
            cur = Observation(ts=m.group(1), app=m.group(2), strategy=m.group(3))
            buf = []
        elif line.startswith("## "):
            # session start/end banner — flush any in-progress observation
            if cur is not None:
                cur.body = "\n".join(buf).strip()
                obs.append(cur); cur = None; buf = []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        cur.body = "\n".join(buf).strip()
        obs.append(cur)
    return Review(observations=obs)


def load(*, since: str | None = None) -> Review:
    """Load and parse the notes file. ``since`` (HH:MM) keeps only observations
    at/after that time *today*."""
    f = _notes_file()
    if not f.is_file():
        return Review()
    review = parse(f.read_text(encoding="utf-8", errors="replace"))
    if since:
        cutoff = _parse_since(since)
        if cutoff:
            review.observations = [
                o for o in review.observations
                if (dt := _safe_dt(o.ts)) and dt >= cutoff
            ]
    return review


def _parse_since(since: str):
    """Accept an HH:MM (today) or a full ISO timestamp. None if unparseable."""
    s = since.strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", s):
        today = datetime.now().strftime("%Y-%m-%d")
        return _safe_dt(f"{today} {s}:00")
    return _safe_dt(s)


def _safe_dt(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def rollup(review: Review) -> str:
    """Factual, offline summary: span + time-in-app breakdown."""
    if not review.observations:
        return "No watch notes yet — run `python3 -m cognitive_twin.watch` first."
    lines = [f"While you were away: {len(review.observations)} observation(s), "
             f"{review.span}.", "", "Where your time went:"]
    spent = review.time_in_app
    total = sum(m for _, m in spent) or 1.0
    for app, m in spent:
        pct = round(100 * m / total)
        lines.append(f"  · {app} — ~{m:.0f} min ({pct}%)")
    return "\n".join(lines)


def digest(review: Review) -> str:
    """A short, local-only 'what I noticed / what's next' from the twin. Returns
    '' if no local model is reachable (caller falls back to the rollup)."""
    if not review.observations:
        return ""
    try:
        from .llm.openai_client import OpenAIClient, OpenAIError
        from .llm.ollama_client import ChatMessage
    except Exception:
        return ""
    client = OpenAIClient(
        model=os.environ.get("LLM_MODEL", "local-model"),
        host=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        temperature=0.3,
    )
    if not client.is_up():
        return ""
    # Feed the twin a compact transcript (cap size so we stay fast/local).
    parts = []
    for o in review.observations[-40:]:
        line = f"[{o.ts}] {o.app}"
        if o.body:
            snippet = o.body.replace("\n", " ")[:200]
            line += f": {snippet}"
        parts.append(line)
    transcript = "\n".join(parts)[:6000]
    prompt = (
        "These are read-only observations of what the user was doing while away "
        "(app + on-screen excerpts). Give a warm, brief welcome-back note:\n"
        "1) one or two sentences on what they were working on,\n"
        "2) anything worth flagging (an error on screen, an open question),\n"
        "3) a suggested next step or two.\n"
        "Be concise and never invent detail that isn't in the observations.\n\n"
        f"{transcript}"
    )
    try:
        reply = client.chat([ChatMessage(role="user", content=prompt)])
        return (reply.content or "").strip()
    except OpenAIError:
        return ""


def welcome_back(*, since: str | None = None, use_llm: bool = True) -> str:
    """The full 'here's what happened while you were away' string."""
    review = load(since=since)
    roll = rollup(review)
    if not review.observations:
        return roll
    # tasks the watch spotted on screen, still waiting for a keep/ignore
    try:
        from . import shadow
        n = len(shadow.proposals())
        if n:
            roll += (f"\n\nSpotted on screen: {n} possible task(s) — "
                     "`python3 -m cognitive_twin day` to keep or ignore.")
    except Exception:
        pass
    note = digest(review) if use_llm else ""
    if note:
        return "— Welcome back —\n\n" + note + "\n\n" + roll
    return "— Welcome back —\n\n" + roll


def _main(argv: list[str]) -> int:
    if argv and argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    since = None
    use_llm = True
    raw = False
    i = 0
    while i < len(argv):
        if argv[i] == "--since" and i + 1 < len(argv):
            since = argv[i + 1]; i += 2
        elif argv[i] == "--no-llm":
            use_llm = False; i += 1
        elif argv[i] == "--raw":
            raw = True; i += 1
        else:
            i += 1
    if raw:
        review = load(since=since)
        for o in review.observations:
            print(f"[{o.ts}] {o.app} (via {o.strategy})")
            if o.body:
                print("    " + o.body.replace("\n", "\n    "))
        return 0
    print(welcome_back(since=since, use_llm=use_llm))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
