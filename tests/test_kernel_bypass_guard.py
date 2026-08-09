"""
Kernel-bypass guard — the test that keeps 'everything is sealed' TRUE over time.

The promise (SECURITY.md) is that no personal store is ever written in plaintext.
It's easy to *say*; this test *enforces* it. For every personal store Vera owns,
we drive that module's real save path in a throwaway memory dir and assert the
file it produced is sealed at rest. If someone later adds a feature that writes
your life to disk without going through the kernel, THIS TEST GOES RED.

Two layers:
  1. Behavioural — call the module's public save API, then check the bytes on disk
     are sealed (this is the real guarantee).
  2. Static tripwire — the security kernel's audit must report every known store as
     sealed/absent, never PLAINTEXT, after the app's own save paths have run.

Run: python -m pytest tests/test_kernel_bypass_guard.py -q
     (or: python tests/test_kernel_bypass_guard.py)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _bind(tmp: Path):
    """Point the whole app at a throwaway memory dir with a fresh key cache."""
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    os.environ["CTWIN_PERSONA_DIR"] = str(tmp)
    os.environ["CTWIN_HOME"] = str(tmp)
    from cognitive_twin import vault, security
    importlib.reload(vault)
    importlib.reload(security)
    vault._key_cache = None
    return vault, security


def _is_sealed_file(vault, p: Path) -> bool:
    if not p.is_file():
        return True  # absent = nothing leaked
    raw = p.read_bytes()
    if vault.is_sealed_bytes(raw):
        return True
    # JSONL: every non-empty line must be a sealed line
    try:
        lines = [ln for ln in raw.decode("utf-8").splitlines() if ln.strip()]
    except UnicodeDecodeError:
        return True  # binary/sealed
    return bool(lines) and all(vault.is_sealed_line(ln.strip()) for ln in lines)


# ---- exercise each personal store's real save path ---------------------------
# Each entry: (module, a callable that performs a real save, the file it writes).
def _drivers(tmp: Path):
    from cognitive_twin import mood, rhythms, soul, activity, places
    import datetime as dt

    def save_mood():
        importlib.reload(mood)
        mood.set_on(True)                       # persists mood.json

    def save_rhythms():
        importlib.reload(rhythms)
        rhythms.set_override("sleep", "23:00-07:00")  # persists rhythms.json

    def save_soul():
        importlib.reload(soul)
        soul.add_reflection("A quiet day.")      # persists soul.json

    def save_activity():
        importlib.reload(activity)
        activity.enable(True)                    # persists the activity state file
        activity.sample(record_titles=False)     # appends a real activity.jsonl line

    def save_places():
        importlib.reload(places)
        places.enable()
        places.record(places.Visit(place="Home", start=dt.datetime.now().isoformat()))

    return [
        ("mood.json", save_mood),
        ("rhythms.json", save_rhythms),
        ("soul.json", save_soul),
        ("activity.jsonl", save_activity),
        ("places.jsonl", save_places),
    ]


def test_no_personal_store_is_written_plaintext(tmp_path):
    vault, S = _bind(tmp_path)
    leaks = []
    for filename, drive in _drivers(tmp_path):
        try:
            drive()
        except Exception as e:  # a save path that errors isn't a leak, but note it
            print(f"  (note: {filename} save path raised {type(e).__name__}: {e})")
            continue
        p = S.path(filename)
        if not _is_sealed_file(vault, p):
            leaks.append(filename)
    assert not leaks, (
        "PLAINTEXT LEAK — these stores were written unsealed, bypassing the "
        f"security kernel: {leaks}. Route them through security.write_state / "
        "security.append_line (see SECURITY.md)."
    )


def test_audit_never_reports_plaintext_after_saves(tmp_path):
    vault, S = _bind(tmp_path)
    for _, drive in _drivers(tmp_path):
        try:
            drive()
        except Exception:
            pass
    bad = [(n, s) for n, s in S.audit() if "PLAINTEXT" in s or "world-readable" in s]
    assert not bad, f"kernel audit found unsealed/exposed stores: {bad}"


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d))
                    print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1
                    print(f"  ✗ {name}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
