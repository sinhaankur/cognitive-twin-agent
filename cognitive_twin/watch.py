"""
Watch & note — an unattended, read-only observer.

While you're away, Vera periodically reads whatever app you're in (via
app_context, which picks Accessibility vs OCR per app) and appends timestamped
notes to a review file. When you come back, you read the log.

STRICTLY read-only and passive:
  - It NEVER edits files, types, clicks, runs commands, or changes any app.
  - It only observes the screen and writes to its own notes file.
  - It honors the same opt-in gate as the rest of control (CTWIN_CONTROL), plus
    its own explicit start — nothing here runs unless you launch it.

It also stays quiet and cheap:
  - Consecutive identical screens are collapsed (a fingerprint per observation),
    so idle time doesn't fill the log.
  - A max duration and interval bound the run; Ctrl-C stops it any time.

Notes live at ~/.cognitive-twin/watch-notes.md (override with CTWIN_WATCH_FILE).

CLI:
    python3 -m cognitive_twin.watch [--interval 60] [--minutes 60]
                                    [--full] [--summarize]
      --interval   seconds between observations (default 60)
      --minutes    stop after this many minutes (default 60; 0 = until Ctrl-C)
      --full       OCR the whole display, not just the front window
      --summarize  ask the local twin for a one-line note per observation
                   (offline-friendly; skipped if no local model is reachable)
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from . import app_context, control


def _notes_file() -> Path:
    p = os.environ.get("CTWIN_WATCH_FILE")
    if p:
        return Path(p)
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "watch-notes.md"


def _fingerprint(app: str, text: str) -> str:
    """Stable hash of an observation, so we skip logging an unchanged screen."""
    h = hashlib.sha256()
    h.update((app + "\n" + text[:1500]).encode("utf-8", "replace"))
    return h.hexdigest()[:12]


def _summarize(app: str, text: str) -> str:
    """One-line, local-only note about what the user seems to be doing. Returns
    '' if no local model is reachable (the raw excerpt is logged instead)."""
    try:
        from .llm.openai_client import OpenAIClient, OpenAIError
        from .llm.ollama_client import ChatMessage
    except Exception:
        return ""
    client = OpenAIClient(
        model=os.environ.get("LLM_MODEL", "local-model"),
        host=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        temperature=0.2,
    )
    if not client.is_up():
        return ""
    prompt = (
        "In one short sentence, note what the user appears to be doing, and if "
        "you notice anything worth flagging for later (a question, an error on "
        "screen, a next step), add it. Be concise and never invent detail.\n\n"
        f"App: {app}\nScreen:\n{text[:1500]}"
    )
    try:
        reply = client.chat([ChatMessage(role="user", content=prompt)])
        return (reply.content or "").strip().replace("\n", " ")
    except OpenAIError:
        return ""


def observe_once(*, scope: str = "window", summarize: bool = False) -> dict:
    """Take one read-only observation of the active app. Returns a dict with the
    app, the read text, an optional summary, and a fingerprint."""
    ctx = app_context.read_active(scope=scope, max_chars=2000)
    text = ctx.text or ""
    note = _summarize(ctx.app, text) if (summarize and ctx.app and not text.startswith("[")) else ""
    return {
        "app": ctx.app,
        "strategy": ctx.strategy,
        "text": text,
        "note": note,
        "fp": _fingerprint(ctx.app, text),
    }


def _append_note(obs: dict) -> None:
    f = _notes_file()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"### {ts} — {obs['app'] or '(unknown app)'}  _(via {obs['strategy']})_"]
    if obs["note"]:
        lines.append(obs["note"])
    body = (obs["text"] or "").strip()
    if body and not body.startswith("["):
        excerpt = body[:400] + ("…" if len(body) > 400 else "")
        lines.append("\n> " + excerpt.replace("\n", "\n> "))
    elif not obs["note"]:
        lines.append("_(no readable on-screen text)_")
    with f.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n\n")


def watch(*, interval: float = 60.0, minutes: float = 60.0,
          scope: str = "window", summarize: bool = False) -> int:
    """Run the watch loop until the time budget is spent or Ctrl-C. Returns the
    number of distinct observations logged. Read-only throughout."""
    control.enable(True)  # launching watch is an explicit opt-in
    f = _notes_file()
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"## Watch session started {started} "
                 f"(every {int(interval)}s, read-only)\n\n")
    print(f"Watching (read-only) every {int(interval)}s — notes → {f}")
    print("Nothing is edited or run. Ctrl-C to stop.")

    deadline = time.time() + minutes * 60 if minutes and minutes > 0 else None
    last_fp = None
    logged = 0
    try:
        while True:
            obs = observe_once(scope=scope, summarize=summarize)
            if obs["fp"] != last_fp and (obs["app"] or obs["text"]):
                _append_note(obs)
                last_fp = obs["fp"]
                logged += 1
                print(f"  · noted {obs['app'] or '(unknown)'} ({logged})")
            if deadline and time.time() >= deadline:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"## Watch session ended {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                 f"— {logged} observation(s)\n\n")
    print(f"Done — {logged} observation(s) logged to {f}")
    return logged


def _main(argv: list[str]) -> int:
    if argv and argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    interval = 60.0
    minutes = 60.0
    scope = "window"
    summarize = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--interval" and i + 1 < len(argv):
            interval = float(argv[i + 1]); i += 2
        elif a == "--minutes" and i + 1 < len(argv):
            minutes = float(argv[i + 1]); i += 2
        elif a == "--full":
            scope = "full"; i += 1
        elif a == "--summarize":
            summarize = True; i += 1
        else:
            i += 1
    watch(interval=interval, minutes=minutes, scope=scope, summarize=summarize)
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
