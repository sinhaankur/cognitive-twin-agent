"""
recipe — shareable, reviewable automation definitions. Import, inspect, then run.

Anyone can set up an automation without writing code: an automation is a small
JSON **recipe** (a name, ordered steps, an optional schedule) that you import from
a file or a link. Nothing runs on import — the recipe is stored sealed and shown
to you for REVIEW first. You approve it, and only then can it run. This is the
safe half of "set up automation from a link": you're importing a config you can
read, not handing a tool blind access to a site.

A recipe's steps are a small, allow-listed vocabulary — no arbitrary code:
    {"action": "open",   "url": "https://…"}         open a page
    {"action": "click",  "selector": "#book"}         click an element
    {"action": "fill",   "selector": "#q", "text": "…"}
    {"action": "waitFor","selector": ".ready"}
    {"action": "readText","selector": ".result", "as": "result"}
    {"action": "notify", "text": "done: {result}"}     tell you the outcome
Anything outside this vocabulary is rejected at import — a recipe can't smuggle in
shell commands or logins to sites we refuse.

Recipes are stored sealed (security kernel). Untrusted recipes start
``approved=false`` and REFUSE to run until you approve them. Destructive-looking
recipes (submit/purchase/delete/pay) are flagged for extra scrutiny.

CLI:
    python3 -m cognitive_twin.automations.recipe import <file-or-url>
    python3 -m cognitive_twin.automations.recipe list
    python3 -m cognitive_twin.automations.recipe show <name>
    python3 -m cognitive_twin.automations.recipe approve <name>
    python3 -m cognitive_twin.automations.recipe remove <name>

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .. import security

_DB = "automations.jsonl"

# The only step actions a recipe may contain. Read + navigate + fill + notify —
# deliberately NO "runShell", NO credential entry, NO submit-to-arbitrary-host.
ALLOWED_ACTIONS = {"open", "click", "fill", "waitFor", "readText", "notify", "wait"}

# Hosts we refuse to drive programmatically (ToS / anti-automation), same policy
# as the careers job reader.
BLOCKED_HOSTS = ("linkedin.com", "indeed.com", "glassdoor.com")

# Words that mark a recipe as doing something outward/irreversible — flagged so
# you look twice before approving.
_SENSITIVE = re.compile(r"\b(submit|purchase|buy|pay|checkout|delete|remove|"
                        r"confirm|book|reserve|apply|send)\b", re.I)


@dataclass
class Recipe:
    name: str
    steps: list[dict[str, Any]]
    description: str = ""
    schedule: str = ""            # optional cron-ish hint; the runner decides
    source: str = ""              # where it came from (file/url)
    approved: bool = False        # imported recipes must be approved to run
    sensitive: bool = False       # touches submit/pay/book/etc.
    created: str = ""

    def targets(self) -> list[str]:
        return [s["url"] for s in self.steps if s.get("action") == "open" and s.get("url")]


class RecipeError(RuntimeError):
    pass


# ── validation (the safety gate) ───────────────────────────────────────────────
def _validate(obj: dict[str, Any]) -> Recipe:
    if not isinstance(obj, dict):
        raise RecipeError("recipe must be a JSON object")
    name = str(obj.get("name", "")).strip()
    if not name:
        raise RecipeError("recipe needs a name")
    steps = obj.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RecipeError("recipe needs a non-empty steps list")

    sensitive = False
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise RecipeError(f"step {i} is not an object")
        action = step.get("action")
        if action not in ALLOWED_ACTIONS:
            raise RecipeError(f"step {i}: action '{action}' not allowed "
                              f"(allowed: {', '.join(sorted(ALLOWED_ACTIONS))})")
        if action == "open":
            url = str(step.get("url", ""))
            host = re.sub(r"^https?://", "", url).split("/")[0].lower()
            if any(b in host for b in BLOCKED_HOSTS):
                raise RecipeError(f"step {i}: refuses to automate {host} (ToS)")
        blob = json.dumps(step)
        if _SENSITIVE.search(blob):
            sensitive = True

    import datetime as dt
    return Recipe(name=name, steps=steps,
                  description=str(obj.get("description", "")),
                  schedule=str(obj.get("schedule", "")),
                  source=str(obj.get("source", "")),
                  approved=False, sensitive=sensitive,
                  created=dt.datetime.now().isoformat(timespec="seconds"))


# ── import from file or URL ────────────────────────────────────────────────────
def import_recipe(source: str) -> Recipe:
    """Load + validate a recipe from a local file or an https URL. Stores it
    UNAPPROVED. Never runs anything."""
    raw = _load(source)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RecipeError(f"not valid JSON: {e}")
    obj.setdefault("source", source)
    recipe = _validate(obj)
    _put(recipe)
    return recipe


def _load(source: str) -> str:
    if re.match(r"^https?://", source):
        import urllib.request
        req = urllib.request.Request(source, headers={"User-Agent": "life-recipe-import"})
        with urllib.request.urlopen(req, timeout=15) as r:  # a config file, not a site to drive
            return r.read().decode("utf-8", "replace")
    from pathlib import Path
    return Path(source).expanduser().read_text(encoding="utf-8")


# ── sealed storage ─────────────────────────────────────────────────────────────
def _path():
    return security.path(_DB)


def read_all() -> list[Recipe]:
    out = []
    for data in security.read_lines(_path()):
        try:
            out.append(Recipe(**data))
        except Exception:
            continue
    return out


def get(name: str) -> Recipe | None:
    return next((r for r in read_all() if r.name == name), None)


def _put(recipe: Recipe) -> None:
    others = [r for r in read_all() if r.name != recipe.name]
    _rewrite(others + [recipe])


def _rewrite(recipes: list[Recipe]) -> None:
    p = _path()
    p.unlink(missing_ok=True)
    for r in recipes:
        security.append_line(p, asdict(r))


def approve(name: str) -> Recipe | None:
    recipes = read_all()
    for r in recipes:
        if r.name == name:
            r.approved = True
            _rewrite(recipes)
            return r
    return None


def remove(name: str) -> bool:
    keep = [r for r in read_all() if r.name != name]
    if len(keep) == len(read_all()):
        return False
    _rewrite(keep)
    return True


# ── human-readable review (what you see before approving) ──────────────────────
def review(recipe: Recipe) -> str:
    lines = [f"Automation: {recipe.name}",
             f"  {recipe.description}" if recipe.description else "",
             f"  Source: {recipe.source or 'local'}",
             f"  Status: {'APPROVED' if recipe.approved else 'NOT approved (review before running)'}"]
    if recipe.sensitive:
        lines.append("  ⚠ This automation submits/books/pays/sends — review carefully.")
    if recipe.schedule:
        lines.append(f"  Schedule: {recipe.schedule}")
    lines.append("  Steps:")
    for i, s in enumerate(recipe.steps, 1):
        lines.append(f"    {i}. {_describe_step(s)}")
    tgts = recipe.targets()
    if tgts:
        lines.append("  Touches: " + ", ".join(sorted(set(tgts))))
    return "\n".join(l for l in lines if l)


def _describe_step(s: dict[str, Any]) -> str:
    a = s.get("action")
    if a == "open":     return f"open {s.get('url', '')}"
    if a == "click":    return f"click {s.get('selector', '')}"
    if a == "fill":     return f"fill {s.get('selector', '')} = “{s.get('text', '')}”"
    if a == "waitFor":  return f"wait for {s.get('selector', '')}"
    if a == "readText": return f"read {s.get('selector', '')} → {s.get('as', 'value')}"
    if a == "notify":   return f"notify: {s.get('text', '')}"
    if a == "wait":     return f"wait {s.get('ms', 500)}ms"
    return json.dumps(s)


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"
    args = argv[1:]
    if cmd == "import":
        if not args:
            print("usage: import <file-or-url>"); return 2
        try:
            r = import_recipe(args[0])
        except RecipeError as e:
            print(f"✗ rejected: {e}"); return 1
        except Exception as e:
            print(f"✗ couldn't import: {e}"); return 1
        print("✓ Imported (NOT yet approved). Review it, then approve to run:\n")
        print(review(r))
        print(f"\n  approve with: recipe approve {r.name}")
        return 0
    if cmd == "list":
        rs = read_all()
        if not rs:
            print("No automations yet. Import one: `recipe import <file-or-url>`"); return 0
        for r in rs:
            flag = "✓" if r.approved else "•"
            warn = " ⚠" if r.sensitive else ""
            print(f"  {flag} {r.name}{warn} — {len(r.steps)} step(s)  {r.description[:40]}")
        return 0
    if cmd == "show":
        r = get(args[0]) if args else None
        print(review(r) if r else "not found"); return 0 if r else 1
    if cmd == "approve":
        r = approve(args[0]) if args else None
        print(f"✓ approved '{r.name}' — it can run now." if r else "not found")
        return 0 if r else 1
    if cmd == "remove":
        print("✓ removed" if args and remove(args[0]) else "not found"); return 0
    print("usage: recipe [import|list|show|approve|remove]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
