"""
run — execute an APPROVED recipe, safely, with a dry-run first.

This is the only place a recipe's steps actually run. It refuses to run anything
that isn't approved, does a dry-run (print the plan) unless you pass --go, shows
each step as it happens, and drives a real browser via Playwright (the same engine
the booker uses). Read/navigate/fill/notify only — the recipe vocabulary can't
express a shell command or a login to a refused host (validated at import).

Playwright is optional: if it isn't installed we explain how, rather than fail
opaquely. Nothing runs on your account without an approved recipe + an explicit
--go.

CLI:
    python3 -m cognitive_twin.automations.run <name>          # dry-run (plan only)
    python3 -m cognitive_twin.automations.run <name> --go      # actually run it

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import sys

from .recipe import get, review, Recipe


class RunError(RuntimeError):
    pass


def _fill_template(text: str, vars: dict) -> str:
    for k, v in vars.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def dry_run(recipe: Recipe) -> str:
    return "DRY RUN — nothing executed:\n" + review(recipe)


def run(name: str, *, go: bool = False) -> dict:
    r = get(name)
    if not r:
        raise RunError(f"no automation named '{name}'")
    if not go:
        return {"status": "dry-run", "plan": dry_run(r)}
    if not r.approved:
        raise RunError(f"'{name}' isn't approved yet — review it and "
                       f"`recipe approve {name}` first.")

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise RunError("Playwright isn't installed. Install it to run browser "
                       "automations: `pip install playwright && playwright install chromium`.")

    vars: dict = {}
    executed = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            for i, step in enumerate(r.steps, 1):
                action = step.get("action")
                if action == "open":
                    page.goto(step["url"], wait_until="domcontentloaded", timeout=40000)
                elif action == "click":
                    page.click(step["selector"], timeout=15000)
                elif action == "fill":
                    page.fill(step["selector"], _fill_template(step.get("text", ""), vars), timeout=15000)
                elif action == "waitFor":
                    page.wait_for_selector(step["selector"], timeout=15000)
                elif action == "wait":
                    page.wait_for_timeout(int(step.get("ms", 500)))
                elif action == "readText":
                    txt = page.text_content(step["selector"], timeout=15000) or ""
                    vars[step.get("as", "value")] = txt.strip()
                elif action == "notify":
                    msg = _fill_template(step.get("text", ""), vars)
                    _notify(msg)
                    vars["_last_notify"] = msg
                executed.append({"step": i, "action": action})
        finally:
            browser.close()
    return {"status": "ran", "steps": len(executed), "vars": vars}


def _notify(msg: str) -> None:
    print(f"  🔔 {msg}")
    try:
        import subprocess
        safe = msg.replace('"', '\\"')
        subprocess.run(["osascript", "-e",
                        f'display notification "{safe}" with title "Automation"'],
                       capture_output=True, timeout=5)
    except Exception:
        pass


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: run <name> [--go]"); return 2
    name = argv[0]
    go = "--go" in argv
    try:
        r = run(name, go=go)
    except RunError as e:
        print(f"✗ {e}"); return 1
    if r["status"] == "dry-run":
        print(r["plan"])
        print(f"\n  to actually run it: run {name} --go")
    else:
        print(f"✓ ran {name}: {r['steps']} step(s) executed.")
        if r["vars"]:
            for k, v in r["vars"].items():
                if not k.startswith("_"):
                    print(f"    {k} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
