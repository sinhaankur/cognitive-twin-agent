"""
Twin Council tests — one question, every twin answers as themselves.

Offline: the model is injected, so no Ollama is needed. We prove that the
council (a) asks each twin, (b) resolves each twin's *own* persona while asking
(so takes are labelled by the right person), (c) survives one twin failing, and
(d) leaves the active-twin selection + env untouched afterwards.

Run: python -m pytest tests/ -q   (or: python tests/test_council.py)
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh_home():
    tmp = tempfile.mkdtemp()
    os.environ["CTWIN_HOME"] = tmp
    os.environ.pop("CTWIN_MEMORY_DIR", None)
    os.environ.pop("CTWIN_PERSONA_DIR", None)
    import cognitive_twin.twins as twins
    importlib.reload(twins)
    return tmp, twins


def _seed_two_twins():
    """Anita + Dad, each with a distinct persona. Returns (twins, persona)."""
    _tmp, twins = _fresh_home()
    import cognitive_twin.persona as persona
    import cognitive_twin.council as council
    for m in (persona, council):
        importlib.reload(m)
    twins.activate("Anita")
    persona.save(persona.Persona(name="Anita"))
    twins.activate("Dad")
    persona.save(persona.Persona(name="Dad"))
    twins.activate("Anita")  # Anita is the active twin going in
    return twins, persona, council


def test_council_asks_every_twin_as_themselves():
    twins, persona, council = _seed_two_twins()

    # The injected `ask` reads whoever's persona is currently active — proving
    # the council re-points the env at each twin before asking.
    def fake_ask(agent, question):
        who = persona.load().name
        return (f"{who} says: {question}", {"model": "fake-model"})

    result = council.convene(
        "what should I do?",
        build_agent=lambda *a, **k: object(),  # agent is unused by fake_ask
        ask=fake_ask,
    )

    names = sorted(t.name for t in result.takes)
    assert names == ["Anita", "Dad"]
    # each take is answered in that twin's own voice/identity
    by_name = {t.name: t for t in result.takes}
    assert by_name["Anita"].answer == "Anita says: what should I do?"
    assert by_name["Dad"].answer == "Dad says: what should I do?"
    assert by_name["Anita"].model == "fake-model"
    assert result.ok() == result.takes  # nobody errored
    print("✓ council: every twin answers as themselves, from its own persona")


def test_council_restores_active_twin_and_env():
    twins, persona, council = _seed_two_twins()
    before_active = twins.active()
    before_env = os.environ.get("CTWIN_MEMORY_DIR")

    council.convene(
        "hello",
        build_agent=lambda *a, **k: object(),
        ask=lambda agent, q: ("ok", None),
    )

    assert twins.active() == before_active  # active twin unchanged
    assert os.environ.get("CTWIN_MEMORY_DIR") == before_env  # env restored
    print("✓ council: leaves the active twin + env exactly as it found them")


def test_council_survives_one_twin_failing():
    twins, persona, council = _seed_two_twins()

    def flaky_ask(agent, question):
        who = persona.load().name
        if who == "Dad":
            raise RuntimeError("model unreachable")
        return (f"{who} answer", {"model": "m"})

    result = council.convene(
        "advice?",
        build_agent=lambda *a, **k: object(),
        ask=flaky_ask,
    )

    by_name = {t.name: t for t in result.takes}
    assert by_name["Anita"].error is None and by_name["Anita"].answer == "Anita answer"
    assert by_name["Dad"].error and "unreachable" in by_name["Dad"].error
    # ok() filters out the failed twin; the council still returns the good take
    assert [t.name for t in result.ok()] == ["Anita"]
    # render doesn't crash on a mixed result and shows the failure inline
    text = council.render(result)
    assert "couldn't answer" in text and "Anita answer" in text
    print("✓ council: one twin failing doesn't sink the rest")


def test_council_subset_via_twin_slugs():
    twins, persona, council = _seed_two_twins()
    result = council.convene(
        "just you",
        twin_slugs=["anita"],
        build_agent=lambda *a, **k: object(),
        ask=lambda agent, q: (persona.load().name, None),
    )
    assert [t.name for t in result.takes] == ["Anita"]
    print("✓ council: can convene a chosen subset of twins")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall council tests passed.")
