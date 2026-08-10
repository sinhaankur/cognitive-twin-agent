"""
record — demonstrate a task once; save it as a reviewable recipe.

This is the safe "give it click/screen access" path: a real browser opens, YOU do
the task (click, type, navigate), and it records those exact actions. When you
close the window it saves them as a recipe (unapproved, like any import) that you
review and can edit before it ever replays. It replays ONLY what you demonstrated
— it never watches your screen continuously and never acts on its own.

Under the hood it launches Playwright's recorder (codegen). We start it on a URL
you give, capture the generated steps, translate the safe subset into our recipe
vocabulary, and store it. Anything the recorder captured that isn't in our
allow-list (e.g. a raw keypress we can't model) is dropped with a note, so a
recorded recipe is always one you can read.

CLI:
    python3 -m cognitive_twin.automations.record start <name> --url https://…

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import re
import sys

from .recipe import Recipe, _put, ALLOWED_ACTIONS


class RecordError(RuntimeError):
    pass


# Playwright codegen emits Python like:  page.goto("…"),  page.click("#x"),
# page.fill("#q", "text"),  page.get_by_role(...).click().  We translate the
# simple, selector-based calls into our recipe steps; skip the rest with a note.
_GOTO = re.compile(r'page\.goto\(\s*["\'](.+?)["\']')
_CLICK = re.compile(r'page\.click\(\s*["\'](.+?)["\']')
_FILL = re.compile(r'page\.fill\(\s*["\'](.+?)["\']\s*,\s*["\'](.*?)["\']')
_WAIT = re.compile(r'page\.wait_for_selector\(\s*["\'](.+?)["\']')


def _steps_from_codegen(code: str) -> tuple[list[dict], int]:
    steps: list[dict] = []
    skipped = 0
    for line in code.splitlines():
        line = line.strip()
        if not line.startswith("page."):
            continue
        m = _GOTO.search(line)
        if m:
            steps.append({"action": "open", "url": m.group(1)}); continue
        m = _FILL.search(line)
        if m:
            steps.append({"action": "fill", "selector": m.group(1), "text": m.group(2)}); continue
        m = _CLICK.search(line)
        if m:
            steps.append({"action": "click", "selector": m.group(1)}); continue
        m = _WAIT.search(line)
        if m:
            steps.append({"action": "waitFor", "selector": m.group(1)}); continue
        # get_by_role / press / other richer calls — can't model safely, skip.
        skipped += 1
    return steps, skipped


def start(name: str, *, url: str) -> Recipe:
    """Open the recorder on ``url``, let the user demonstrate, then save the
    captured steps as an UNAPPROVED recipe."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise RecordError("Playwright isn't installed. `pip install playwright && "
                          "playwright install chromium` to record automations.")

    # Playwright's Python API doesn't expose codegen directly; the supported path
    # is the CLI recorder writing a script we then parse.
    import subprocess
    import tempfile
    from pathlib import Path

    out = Path(tempfile.mkdtemp()) / "recorded.py"
    print("A browser will open. Do the task you want to automate, then CLOSE the "
          "window to save it.")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "codegen", "--target", "python",
             "-o", str(out), url],
            timeout=1800,
        )
    except FileNotFoundError:
        raise RecordError("playwright CLI not found — `pip install playwright`.")
    except subprocess.TimeoutExpired:
        raise RecordError("recording timed out.")

    if not out.is_file():
        raise RecordError("nothing was recorded.")
    steps, skipped = _steps_from_codegen(out.read_text(encoding="utf-8"))
    if not steps:
        raise RecordError("no replayable steps captured (try clicking elements with "
                          "stable ids).")

    import datetime as dt
    recipe = Recipe(
        name=name, steps=steps,
        description=f"Recorded {dt.date.today().isoformat()}"
                    + (f" ({skipped} action(s) not captured)" if skipped else ""),
        source=f"recorded:{url}", approved=False,
        sensitive=any(a in str(steps).lower() for a in
                      ("submit", "purchase", "pay", "book", "confirm", "apply")),
        created=dt.datetime.now().isoformat(timespec="seconds"),
    )
    _put(recipe)
    return recipe


def _main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "start":
        print("usage: record start <name> --url https://…"); return 2
    name = argv[1]
    if "--url" not in argv:
        print("give --url to start recording on"); return 2
    url = argv[argv.index("--url") + 1]
    try:
        r = start(name, url=url)
    except RecordError as e:
        print(f"✗ {e}"); return 1
    from .recipe import review
    print(f"✓ Recorded '{r.name}' ({len(r.steps)} steps, NOT approved). Review:\n")
    print(review(r))
    print(f"\n  approve to allow replay: recipe approve {r.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
