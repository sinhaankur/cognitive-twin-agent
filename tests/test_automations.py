"""
Automation tests — recipe import/validation, the approval gate, and record parse.

Asserts the safety model: valid recipes import UNAPPROVED; forbidden actions and
blocked hosts (LinkedIn) are rejected; sensitive recipes are flagged; runs refuse
until approved; and the record codegen parser keeps only the safe, modelable
steps. All offline (no browser). Sealed at rest.

Run: python -m pytest tests/test_automations.py -q
     (or: python tests/test_automations.py)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security
    from cognitive_twin.automations import recipe, run, record
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(recipe)
    importlib.reload(run)
    importlib.reload(record)
    vault._key_cache = None
    return recipe, run, record


def _write(tmp: Path, obj) -> str:
    p = tmp / "r.json"
    p.write_text(json.dumps(obj))
    return str(p)


def test_import_is_unapproved_and_sealed(tmp_path):
    R, _, _ = _fresh(tmp_path)
    src = _write(tmp_path, {"name": "weather", "steps": [
        {"action": "open", "url": "https://example.com"},
        {"action": "readText", "selector": ".t", "as": "t"}]})
    r = R.import_recipe(src)
    assert r.approved is False
    raw = R._path().read_bytes()
    assert b"example.com" not in raw            # sealed


def test_forbidden_action_rejected(tmp_path):
    R, _, _ = _fresh(tmp_path)
    src = _write(tmp_path, {"name": "evil", "steps": [{"action": "runShell", "cmd": "x"}]})
    try:
        R.import_recipe(src)
    except R.RecipeError:
        return
    assert False, "expected rejection of forbidden action"


def test_blocked_host_rejected(tmp_path):
    R, _, _ = _fresh(tmp_path)
    src = _write(tmp_path, {"name": "li", "steps": [
        {"action": "open", "url": "https://www.linkedin.com/jobs"}]})
    try:
        R.import_recipe(src)
    except R.RecipeError as e:
        assert "linkedin" in str(e).lower()
        return
    assert False, "expected LinkedIn rejection"


def test_sensitive_flagged(tmp_path):
    R, _, _ = _fresh(tmp_path)
    src = _write(tmp_path, {"name": "buy", "steps": [
        {"action": "open", "url": "https://shop.example.com"},
        {"action": "click", "selector": "#purchase"}]})
    r = R.import_recipe(src)
    assert r.sensitive is True


def test_run_refuses_until_approved(tmp_path):
    R, Run, _ = _fresh(tmp_path)
    src = _write(tmp_path, {"name": "w", "steps": [{"action": "open", "url": "https://x.com"}]})
    R.import_recipe(src)
    # dry-run always allowed
    assert Run.run("w", go=False)["status"] == "dry-run"
    # go before approve → refused
    try:
        Run.run("w", go=True)
    except Run.RunError as e:
        assert "approve" in str(e).lower()
        return
    # if playwright is installed it may reach the launch; either way not a silent run
    assert False, "expected refusal before approval"


def test_record_parser_keeps_safe_steps(tmp_path):
    _, _, Rec = _fresh(tmp_path)
    code = (
        'page.goto("https://example.com/login")\n'
        'page.fill("#user", "alice")\n'
        'page.click("#submit")\n'
        'page.get_by_role("button", name="X").click()\n'   # unmodelable → skipped
        'page.wait_for_selector(".done")\n'
    )
    steps, skipped = Rec._steps_from_codegen(code)
    actions = [s["action"] for s in steps]
    assert actions == ["open", "fill", "click", "waitFor"]
    assert skipped == 1


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d)); print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1; print(f"  ✗ {name}: {e}")
                except Exception as e:
                    failures += 1; print(f"  ✗ {name}: {type(e).__name__}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
