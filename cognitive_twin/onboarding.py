"""
First-run onboarding — a warm, guided setup for non-technical people.

The agent has a lot of power behind env vars and subcommands. A newcomer
shouldn't need to know any of that to make their twin. This wizard walks them
through it in plain language:

  1. name the twin (creates + activates it)
  2. describe who they are (reuses persona.setup)
  3. optionally give them a voice (a recording to clone, locally)
  4. optionally mark the twin private (kept on this machine, never shareable)

It's idempotent and skippable: a marker file records that onboarding ran, so the
CLI only *offers* it on a truly fresh install and never nags. Everything it does
is also reachable from the normal subcommands — this is a friendlier front door,
not a separate path.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from . import persona, twins, voice_clone


def _home() -> Path:
    return Path(os.environ.get("CTWIN_HOME", Path.home() / ".cognitive-twin"))


_DONE = "onboarded.flag"


def has_onboarded() -> bool:
    return (_home() / _DONE).is_file()


def _mark_done() -> None:
    try:
        f = _home() / _DONE
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("onboarding completed\n", encoding="utf-8")
        os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def is_fresh_install() -> bool:
    """True when there are no twins yet AND onboarding hasn't run — the only time
    we proactively offer the wizard."""
    return not has_onboarded() and not twins.list_twins()


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return v or default


def _yes(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    try:
        v = input(f"{prompt} [{d}] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not v:
        return default
    return v in {"y", "yes"}


def run() -> int:
    """The guided first-run flow. Returns a CLI exit code."""
    print("\n  Welcome. Let's set up your twin — a digital version of someone")
    print("  you care about, living entirely on this machine.\n")

    # 1) name → create + activate the twin
    name = _ask("What's their name (e.g. Anita)")
    while not name:
        print("  (a name helps the twin feel like them — even a first name is fine)")
        name = _ask("Their name")
    twin_slug = twins.create(name)  # creates + marks active in the registry
    twins.activate(twin_slug)       # point persona/voice/memory env at this twin
    print(f"\n  Created and activated the twin “{name}”.\n")

    # 2) persona — reuse the guided flow, pre-seeding the name
    print("  Now, who are they? Press Enter to skip any question.\n")
    p = persona.load()
    if not p.name:
        p.name = name
    p.about = persona._ask("One line about them", p.about)
    p.traits = persona._ask_list("Personality traits", p.traits)
    p.likes = persona._ask_list("Things they like", p.likes)
    p.dislikes = persona._ask_list("Things they dislike", p.dislikes)
    p.values = persona._ask_list("What they value", p.values)
    p.style = persona._ask("How they talk", p.style)
    persona.save(p)
    # the twin's persona is on by nature of onboarding — but persona.is_enabled is
    # a separate opt-in elsewhere; we don't force any cross-feature flag here.
    print("\n  Saved their persona.\n")

    # 3) voice (optional)
    if _yes("Do you have a recording of their voice to clone (local, private)?", False):
        path = _ask("  Path to the audio file (wav/mp3/m4a)")
        if path:
            res = voice_clone.set_reference(path, person=name)
            if res.get("ok"):
                if res.get("ready"):
                    print("  Voice set up — replies can be spoken in their voice.\n")
                else:
                    print("  Voice sample saved. To enable cloning, run "
                          "scripts/setup-voice-clone.sh once (it installs the local engine).\n")
            else:
                print(f"  Couldn't use that file: {res.get('error')}\n")
    else:
        print("  No problem — you can add a voice later:")
        print("    python -m cognitive_twin.voice_clone set /path/to/voice.wav \"" + name + "\"\n")

    # 4) private?
    if _yes("Keep this twin private to this machine (never exportable/shareable)?", False):
        twins.set_private(twin_slug, True)
        print("  Marked private — this twin can't be exported.\n")

    _mark_done()
    print("  All set. Your twin is ready.\n")
    print("  Try:")
    print("    python -m cognitive_twin \"good morning\"     # talk to your twin")
    print("    python -m cognitive_twin twin                # see / switch twins")
    print("    python -m cognitive_twin persona             # review the persona")
    print()
    return 0


def offer() -> bool:
    """On a fresh install, offer the wizard. Returns True if it ran. Declining
    marks onboarding done so we don't ask again."""
    if not is_fresh_install():
        return False
    print("\n  Looks like a fresh start. Set up your twin now? (takes a minute)")
    if _yes("  Start guided setup", True):
        run()
        return True
    _mark_done()
    print("  Okay — run `python -m cognitive_twin setup` anytime to set up your twin.\n")
    return False


if __name__ == "__main__":
    raise SystemExit(run())
