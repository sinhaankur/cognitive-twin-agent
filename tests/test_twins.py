"""
Multiple-twins tests — isolation, switching, and legacy migration.

Each test uses a throwaway CTWIN_HOME and clears any pinned CTWIN_MEMORY_DIR so
twins.activate() drives the storage root (as it does in the real CLI). Offline,
no Ollama.

Run: python -m pytest tests/ -q   (or: python tests/test_twins.py)
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh_home():
    """A clean CTWIN_HOME with no pinned dirs. Returns the temp path."""
    tmp = tempfile.mkdtemp()
    os.environ["CTWIN_HOME"] = tmp
    os.environ.pop("CTWIN_MEMORY_DIR", None)
    os.environ.pop("CTWIN_PERSONA_DIR", None)
    # reload modules so their module-level state + the migration flag reset
    import cognitive_twin.twins as twins
    importlib.reload(twins)
    return tmp, twins


def test_create_switch_isolation():
    _tmp, twins = _fresh_home()
    import cognitive_twin.persona as persona
    importlib.reload(persona)

    assert twins.list_twins() == []
    twins.create("Anita")
    twins.create("Dad")
    assert set(twins.list_twins()) == {"anita", "dad"}
    assert twins.active() == "dad"  # last created is active

    # save a distinct persona under each twin, prove they don't bleed
    twins.activate("dad")
    persona.save(persona.Persona(name="Dad"))
    twins.activate("anita")
    persona.save(persona.Persona(name="Anita"))

    twins.activate("dad")
    assert persona.load().name == "Dad"
    twins.activate("anita")
    assert persona.load().name == "Anita"
    print("✓ twins: create, switch, and per-twin isolation")


def test_remove_active_reassigns():
    _tmp, twins = _fresh_home()
    twins.create("a")
    twins.create("b")  # active
    assert twins.active() == "b"
    assert twins.remove("b") is True
    # removing the active twin reassigns to a remaining one
    assert twins.active() == "a"
    assert twins.remove("a") is True
    assert twins.active() is None
    print("✓ twins: removing the active twin reassigns / clears")


def test_legacy_flat_migrates_to_default():
    tmp, twins = _fresh_home()
    home = Path(tmp)
    # simulate a pre-multi-twin flat install
    (home / "persona.json").write_text('{"name":"Legacy"}', encoding="utf-8")
    (home / "voice").mkdir()
    (home / "voice" / "reference.wav").write_text("x", encoding="utf-8")

    # any registry call triggers the one-time migration
    assert twins.list_twins() == ["default"]
    assert twins.active() == "default"
    moved = home / "twins" / "default"
    assert (moved / "persona.json").is_file()
    assert (moved / "voice" / "reference.wav").is_file()
    assert not (home / "persona.json").exists()  # flat copy removed
    print("✓ twins: legacy flat layout migrates to 'default' without data loss")


def test_private_twin_refuses_export():
    tmp, twins = _fresh_home()
    import cognitive_twin.persona as persona
    import cognitive_twin.twin_package as pkg
    import importlib
    importlib.reload(persona)
    importlib.reload(pkg)

    twins.activate("Anita")
    persona.save(persona.Persona(name="Anita"))
    twins.set_private("Anita", True)
    assert twins.is_private("Anita") is True

    res = pkg.export_twin("Anita", str(Path(tmp) / "anita.twin"))
    assert res["ok"] is False
    assert "private" in res["error"]
    assert not (Path(tmp) / "anita.twin").exists()  # nothing written
    print("✓ package: a private twin is hard-refused for export")


def test_export_import_excludes_private_memory():
    tmp, twins = _fresh_home()
    import cognitive_twin.persona as persona
    import cognitive_twin.memory as memory
    import cognitive_twin.twin_package as pkg
    import importlib
    for m in (persona, memory, pkg):
        importlib.reload(m)

    twins.activate("Mentor")
    persona.save(persona.Persona(name="Mentor", traits=["wise"]))
    memory.record("q", "SECRET private note")  # must not travel

    out = Path(tmp) / "mentor.twin"
    res = pkg.export_twin("Mentor", str(out))
    assert res["ok"] and out.is_file()

    import zipfile
    names = zipfile.ZipFile(out).namelist()
    assert "persona.json" in names
    assert not any("memory" in n for n in names)  # privacy: no memory in package

    imp = pkg.import_twin(str(out), name="Mentor Copy")
    assert imp["ok"] and imp["twin"] == "mentor-copy"
    twins.activate("mentor-copy")
    assert persona.load().name == "Mentor"        # identity carried
    assert memory.summary_for_prompt().strip() == ""  # memory did NOT carry
    print("✓ package: export/import carries identity, never private memory")


def test_onboarding_creates_twin_and_marks_done():
    tmp, twins = _fresh_home()
    import cognitive_twin.persona as persona
    import cognitive_twin.onboarding as onb
    import importlib
    importlib.reload(persona)
    importlib.reload(onb)

    assert onb.is_fresh_install() is True  # nothing yet → wizard would be offered

    # Drive the wizard non-interactively by feeding stdin (name, persona, no
    # voice, not private). Mirrors what a user types.
    import io
    answers = "Grandpa\nkind man\ngentle\nfishing\n\nfamily\nwarm\nn\nn\n"
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(answers)
    try:
        rc = onb.run()
    finally:
        sys.stdin = old_stdin
    assert rc == 0

    assert twins.list_twins() == ["grandpa"]
    twins.activate("grandpa")
    assert persona.load().name == "Grandpa"
    assert onb.has_onboarded() is True
    assert onb.is_fresh_install() is False  # won't nag again
    print("✓ onboarding: guided run creates the twin + persona, marks done")


def test_proactive_opening_reaches_out():
    tmp, twins = _fresh_home()
    import cognitive_twin.persona as persona
    import cognitive_twin.soul as soul
    import cognitive_twin.cli as cli
    import importlib
    for m in (persona, soul, cli):
        importlib.reload(m)

    twins.activate("Anita")
    persona.save(persona.Persona(name="Anita"))
    soul.add_reflection("a thought I had while you were away")

    lines = cli._proactive_opening()
    joined = " ".join(lines)
    # the twin greets BY NAME (proactive, not a static prompt)
    assert "Anita" in joined
    # and surfaces the saved reflection unprompted
    assert "a thought I had while you were away" in joined
    # reading a pending reflection clears it (won't repeat next session)
    assert soul.pending_reflections() == []
    print("✓ proactive: twin greets by name + surfaces an away-thought, then clears it")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall twins tests passed.")
