"""
Shadow — she follows your day.

Vera quietly keeps a day ledger of the things you say you'll do. Mention a task
in conversation — "remind me to…", "I need to…", "todo: …" — and she notes it.
Tell her it's done — "I finished…", "done with…" — and she crosses it off. No
forms, no separate tracker: the tracking happens *in* the conversation, the way
a person who knows you would just remember.

Honest and transparent, like the rest of her mind:
  - A rule layer catches tasks and completions (no model, no dependency — the
    same spirit as the router, email triage, and memory types). It errs toward
    catching *less*: questions and requests to the agent are not your tasks.
  - The ledger is an append-only local file (`shadow.jsonl`, next to memory,
    owner-only 0600). Every state change is an event you can read.
  - No network code in this module; nothing leaves the machine.

What "understanding" means here, concretely:
  - She knows how long a task has been open ("carried 3 days") and says so.
  - The day view links open tasks to the topics you keep raising, so it reads
    like someone who knows what you care about.
  - Open tasks fold into her system prompt, so "what should I focus on?"
    already knows what's on your plate.

Seen, not just heard: the watch observer (watch.py) passes what it reads on
screen through this module too. Explicit markers only — uppercase `TODO:` /
`FIXME:` and unchecked `- [ ]` boxes — become *proposals*, never tasks, until
you keep them. Your screen is none of her business beyond that.

CLI:  python -m cognitive_twin day             # your day, shadowed
      python -m cognitive_twin day add "…"     # note a task yourself
      python -m cognitive_twin day done 2      # cross one off (number or words)
      python -m cognitive_twin day drop 2      # let one go
      python -m cognitive_twin day keep 1      # hold a task she saw on screen
      python -m cognitive_twin day ignore 1    # …or let the sighting pass
      python -m cognitive_twin day clear       # wipe the ledger
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import memory as _memory


def _file() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "shadow.jsonl"


def _secure(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# ---- the rule layer: what counts as a task, what counts as done ---------------
# First-person commitments and explicit reminders only. "can you build X" is a
# request to the agent, not the user's task — deliberately not captured.
_ADD = [
    re.compile(r"\bremind me to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bdon'?t let me forget(?: to)?\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi (?:need|have|want) to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi should\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am) (?:going to|planning to)\s+(.+)", re.IGNORECASE),
    re.compile(r"\btodo:?\s+(.+)", re.IGNORECASE),
    re.compile(r"\badd (?:a )?task:?\s+(.+)", re.IGNORECASE),
]
_DONE = [
    re.compile(r"\b(?:finished|completed|shipped|wrapped up)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(?:i'?m )?done with\s+(.+)", re.IGNORECASE),
    re.compile(r"\bmark\s+(.+?)\s+(?:as\s+)?done\b", re.IGNORECASE),
    re.compile(r"\b(.+?)\s+is (?:done|finished)\b", re.IGNORECASE),
    re.compile(r"\bcross(?:ed)? off\s+(.+)", re.IGNORECASE),
]
# clauses that start with these aren't actionable — "I need to know…" is a
# question, not a commitment
_NOT_A_TASK = {"know", "understand", "think", "say", "see", "hear", "feel",
               "talk", "chat", "ask", "be"}
# don't scan pasted documents — conversation only
_MAX_SCAN = 600


def _words(text: str) -> set[str]:
    """Content words — same filter as memory, so matching agrees on 'signal'."""
    out: set[str] = set()
    for raw in (text or "").lower().split():
        w = "".join(c for c in raw if c.isalnum())
        if len(w) >= 3 and not w.isdigit() and w not in _memory._STOP:
            out.add(w)
    return out


def _key(text: str) -> str:
    """Normalized dedup key: the sorted content words (or the bare text)."""
    ws = _words(text)
    return " ".join(sorted(ws)) if ws else (text or "").lower().strip()


def _clean_clause(clause: str) -> str:
    """Trim a captured clause down to the task itself."""
    c = clause.strip().strip('.!,;:"\'')
    low = c.lower()
    for sep in (" and then ", " after that ", " because ", " so that ", "; "):
        i = low.find(sep)
        if i > 0:
            c = c[:i]
            low = low[:i]
    return c[:120].strip()


def extract_task(text: str) -> str:
    """The task a piece of conversation commits to, or '' if none. Questions
    are never tasks — asking isn't committing."""
    t = (text or "").strip()
    if not t or len(t) > _MAX_SCAN or t.endswith("?"):
        return ""
    for pat in _ADD:
        m = pat.search(t)
        if m:
            clause = _clean_clause(m.group(1))
            first = clause.split()[0].lower().strip("'") if clause.split() else ""
            if len(clause) >= 3 and first not in _NOT_A_TASK:
                return clause
    return ""


def extract_done(text: str) -> str:
    """The thing a piece of conversation says is finished, or ''."""
    t = (text or "").strip()
    if not t or len(t) > _MAX_SCAN or t.endswith("?"):
        return ""
    for pat in _DONE:
        m = pat.search(t)
        if m:
            clause = _clean_clause(m.group(1))
            if len(clause) >= 3:
                return clause
    return ""


# ---- the ledger: append-only events, state by replay ---------------------------
@dataclass
class Task:
    id: str
    text: str
    source: str          # "heard" (from conversation) | "you" (explicit) | "agent"
    created: str         # ISO timestamp
    done: str = ""       # ISO timestamp when completed, else ""
    dropped: bool = False


def _append_event(ev: dict[str, Any]) -> None:
    path = _file()
    existed = path.exists()
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if not existed:
            _secure(path)
    except OSError:
        pass  # the shadow is best-effort; never break the agent over it


def _events() -> list[dict[str, Any]]:
    path = _file()
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def tasks() -> list[Task]:
    """Current state, replayed from the event log — oldest first."""
    by_id: dict[str, Task] = {}
    for ev in _events():
        kind = ev.get("ev")
        tid = ev.get("id", "")
        if kind == "add" and tid and tid not in by_id:
            by_id[tid] = Task(id=tid, text=ev.get("text", ""),
                              source=ev.get("source", "you"),
                              created=ev.get("ts", ""))
        elif kind == "done" and tid in by_id:
            by_id[tid].done = ev.get("ts", "")
        elif kind == "drop" and tid in by_id:
            by_id[tid].dropped = True
    return list(by_id.values())


def open_tasks() -> list[Task]:
    return [t for t in tasks() if not t.done and not t.dropped]


def done_today() -> list[Task]:
    today = _dt.date.today().isoformat()
    return [t for t in tasks() if t.done.startswith(today) and not t.dropped]


# ---- write ---------------------------------------------------------------------
def add(text: str, *, source: str = "you") -> tuple[Task, bool]:
    """Note a task. Returns (task, created) — created is False when an open
    task already covers it (same content words), so hearing the same commitment
    twice never double-books the day."""
    text = (text or "").strip()
    k = _key(text)
    for t in open_tasks():
        if _key(t.text) == k:
            return t, False
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    tid = hashlib.sha256(f"{ts} {text}".encode("utf-8")).hexdigest()[:8]
    task = Task(id=tid, text=text, source=source, created=ts)
    _append_event({"ts": ts, "ev": "add", "id": tid, "text": text, "source": source})
    # a pending sighting of the same task is now answered — resolve it so the
    # day view never shows the same thing as both held and noticed
    for p in proposals():
        if _key(p.text) == k:
            _append_event({"ts": ts, "ev": "keep", "id": p.id})
    return task, True


def complete(task: Task) -> None:
    _append_event({"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                   "ev": "done", "id": task.id})


def drop(task: Task) -> None:
    _append_event({"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                   "ev": "drop", "id": task.id})


def complete_matching(text: str) -> Task | None:
    """Cross off the open task that best matches ``text`` (content-word
    overlap, most shared words wins). None if nothing plausibly matches."""
    q = _words(text)
    if not q:
        return None
    best: Task | None = None
    best_score = 0
    for t in open_tasks():
        score = len(q & _words(t.text))
        if score > best_score:
            best, best_score = t, score
    if best is not None:
        complete(best)
    return best


def observe(text: str) -> str:
    """Listen to one piece of conversation: cross off what it says is finished,
    note what it commits to. Returns a short human note ('' when nothing
    happened) — safe to call twice on the same text (dedup makes the second
    call a no-op). Never raises."""
    try:
        notes: list[str] = []
        done_clause = extract_done(text)
        if done_clause:
            hit = complete_matching(done_clause)
            if hit is not None:
                notes.append(f"crossed off: {hit.text}")
        task_text = extract_task(text)
        if task_text:
            t, created = add(task_text, source="heard")
            if created:
                notes.append(f"noted: {t.text}")
        return " · ".join(notes)
    except Exception:
        return ""


# ---- seen on screen: proposals from the watch observer -------------------------
# The watch (watch.py) is read-only; when it reads your screen it may spot an
# explicit task marker. Those become *proposals* — never tasks — until you keep
# them. Uppercase TODO:/FIXME: and unchecked "- [ ]" boxes only: the honest,
# unambiguous signals. Everything else on your screen is none of her business.
_SEEN_MARKER = re.compile(r"\b(?:TODO|FIXME)\b\s*[:\-–—]\s*(\S.+)")
_SEEN_CHECKBOX = re.compile(r"^\s*[-*]\s*\[ \]\s+(\S.+)$", re.MULTILINE)
_SEEN_CAP = 3          # max new proposals per screen read — never flood the day


@dataclass
class Proposal:
    id: str
    text: str
    app: str             # where it was seen
    ts: str              # ISO timestamp of the sighting
    state: str = "pending"   # pending | kept | ignored


def extract_seen(text: str) -> list[str]:
    """Explicit task markers in a piece of on-screen text. Deliberately narrow:
    OCR text is noisy, and a word like 'todo' in prose is not a marker."""
    t = (text or "")[:4000]
    out: list[str] = []
    for m in list(_SEEN_MARKER.finditer(t)) + list(_SEEN_CHECKBOX.finditer(t)):
        clause = _clean_clause(m.group(1)).rstrip("*/#>–— -").strip()
        if len(clause) >= 3 and _words(clause) and clause not in out:
            out.append(clause)
    return out


def proposals(all_states: bool = False) -> list[Proposal]:
    """Sightings, replayed from the event log — pending only by default."""
    by_id: dict[str, Proposal] = {}
    for ev in _events():
        kind = ev.get("ev")
        pid = ev.get("id", "")
        if kind == "seen" and pid and pid not in by_id:
            by_id[pid] = Proposal(id=pid, text=ev.get("text", ""),
                                  app=ev.get("app", ""), ts=ev.get("ts", ""))
        elif kind == "keep" and pid in by_id:
            by_id[pid].state = "kept"
        elif kind == "ignore" and pid in by_id:
            by_id[pid].state = "ignored"
    ps = list(by_id.values())
    return ps if all_states else [p for p in ps if p.state == "pending"]


def propose(text: str, *, app: str = "") -> tuple[Proposal, bool]:
    """Suggest a task Vera *saw*, without putting it on the plate. Returns
    (proposal, created). Never re-proposes something already sighted — an
    ignore is an answer, not an invitation to nag — and never proposes what's
    already an open task."""
    text = (text or "").strip()
    k = _key(text)
    for p in proposals(all_states=True):
        if _key(p.text) == k:
            return p, False
    for t in open_tasks():
        if _key(t.text) == k:
            return Proposal(id=t.id, text=t.text, app=app, ts=t.created,
                            state="kept"), False
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    pid = hashlib.sha256(f"seen {ts} {text}".encode("utf-8")).hexdigest()[:8]
    _append_event({"ts": ts, "ev": "seen", "id": pid, "text": text, "app": app})
    return Proposal(id=pid, text=text, app=app, ts=ts), True


def propose_from_screen(app: str, text: str) -> list[Proposal]:
    """Scan one read-only screen capture for explicit markers and propose the
    new ones (capped per read). Never raises — the watch must not die over
    the shadow."""
    try:
        new: list[Proposal] = []
        for clause in extract_seen(text):
            p, created = propose(clause, app=app or "")
            if created:
                new.append(p)
            if len(new) >= _SEEN_CAP:
                break
        return new
    except Exception:
        return []


def keep(p: Proposal) -> Task:
    """Accept a sighting: it becomes a real open task (source 'seen')."""
    _append_event({"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                   "ev": "keep", "id": p.id})
    t, _ = add(p.text, source="seen")
    return t


def ignore(p: Proposal) -> None:
    """Decline a sighting. It won't be proposed again."""
    _append_event({"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                   "ev": "ignore", "id": p.id})


# ---- read: the day, rendered ----------------------------------------------------
def _age_label(created: str) -> str:
    try:
        days = (_dt.date.today() - _dt.datetime.fromisoformat(created).date()).days
    except ValueError:
        return ""
    if days <= 0:
        return "today"
    if days == 1:
        return "since yesterday"
    return f"carried {days} days"


def day_view() -> str:
    """Your day, shadowed — open tasks (oldest first, so carried ones surface),
    what got crossed off today, and which tasks touch what you care about."""
    now = _dt.datetime.now()
    header = f"Your day, shadowed — {now.strftime('%A')} {now.day} {now.strftime('%B')}"
    lines = [header, ""]

    topics = set()
    try:
        topics = set(_memory.patterns().get("topics") or [])
    except Exception:
        pass

    op = open_tasks()
    if op:
        lines.append("  On your plate:")
        for i, t in enumerate(op, 1):
            bits = [_age_label(t.created) or "today"]
            if t.source == "heard":
                bits.append("heard in chat")
            touch = _words(t.text) & topics
            if touch:
                bits.append("touches: " + ", ".join(sorted(touch)[:2]))
            lines.append(f"    {i}. {t.text}  ({' · '.join(bits)})")
    else:
        lines.append("  Nothing on your plate — mention a task (\"remind me to…\") "
                     "and I'll hold it.")

    dn = done_today()
    if dn:
        lines.append("")
        lines.append("  Crossed off today:")
        for t in dn:
            lines.append(f"    ✓ {t.text}")

    props = proposals()
    if props:
        lines.append("")
        lines.append("  Noticed on your screen (not on your plate until you say so):")
        for i, p in enumerate(props, 1):
            where = f"seen in {p.app}" if p.app else "seen"
            lines.append(f"    {i}. {p.text}  ({where} · {_age_label(p.ts) or 'today'})")
        lines.append("    → `day keep <n>` to hold one · `day ignore <n>` to let it pass")

    return "\n".join(lines)


def context_for_prompt() -> str:
    """One short block for the system prompt so the twin already knows the
    user's day — local only, never sent off device."""
    op = open_tasks()
    dn = done_today()
    if not op and not dn:
        return ""
    bits = []
    if op:
        head = "; ".join(t.text for t in op[:5])
        more = f" (+{len(op) - 5} more)" if len(op) > 5 else ""
        bits.append(f"open tasks: {head}{more}")
    if dn:
        bits.append("completed today: " + "; ".join(t.text for t in dn[:3]))
    return ("The user's day (from the local task shadow — private): "
            + ". ".join(bits) + ". Weave these in naturally when relevant; don't nag.")


# ---- clear / status --------------------------------------------------------------
def clear() -> bool:
    """Delete the whole ledger. Returns True if a file was removed."""
    path = _file()
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        pass
    return False


def status() -> str:
    op, dn, pr = open_tasks(), done_today(), proposals()
    seen = f", {len(pr)} noticed on screen" if pr else ""
    return (f"day shadow: {len(op)} open, {len(dn)} done today{seen} — "
            f"private, on-device ({_file()})")


if __name__ == "__main__":
    print(day_view())
