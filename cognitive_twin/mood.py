"""
Reflective mood — the contemplative, warm-melancholy tone the user loves in films
like The Darjeeling Limited: family, distance, journeys, and gently letting go.

Important: this contains NO copyrighted dialogue. It's an original description of
a *mood* plus original, in-that-spirit prompt guidance, so Anita's reflections
feel thought-provoking and tender without ever quoting a film.

The mood is opt-in and folds into how she writes 'thoughts of the day' and her
background reflections.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


STATE = "mood.json"
# default on — it suits a twin meant to carry a loved one's warmth
_DEFAULT = True


def is_on() -> bool:
    p = _dir() / STATE
    try:
        if p.is_file():
            return bool(json.loads(p.read_text(encoding="utf-8")).get("reflective", _DEFAULT))
    except (OSError, json.JSONDecodeError):
        pass
    return _DEFAULT


def set_on(on: bool) -> None:
    p = _dir() / STATE
    try:
        p.write_text(json.dumps({"reflective": on}), encoding="utf-8")
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# Original guidance — the *style*, not anyone's words.
MOOD_PROMPT = (
    "# TONE (reflective)\n"
    "Carry a warm, contemplative voice — the wistful tenderness of a slow train "
    "journey through somewhere far from home: aware of distance and of family, "
    "finding meaning in small moments, and at peace with letting things go. Be "
    "gently thought-provoking, never heavy or sentimental. A little quiet wisdom, "
    "offered with love. Keep it brief."
)


def mood_prompt() -> str:
    """The reflective-tone block for the system prompt (empty if turned off)."""
    return MOOD_PROMPT if is_on() else ""


def reflection_style() -> str:
    """A one-line style hint appended to reflection/thought prompts."""
    if not is_on():
        return ""
    return (" Write it in a warm, reflective tone — the kind of quiet, "
            "thought-provoking line that stays with someone, in your own words.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("on", "off"):
        set_on(sys.argv[1] == "on")
        print(f"reflective mood: {'on' if is_on() else 'off'}")
    else:
        print(f"reflective mood: {'on' if is_on() else 'off'}")
        print(mood_prompt())
