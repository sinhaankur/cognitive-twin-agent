"""
Multiple twins on one machine.

A "twin" is a named profile — persona + voice + memory — for one person (your
mom, your dad, a mentor). Each lives in its own folder so they never bleed into
each other, and you switch the *active* twin; every other module then reads that
twin's data transparently.

Layout::

    ~/.cognitive-twin/
      twins/
        anita/          ← one twin: persona.json, memory.jsonl, voice/, media/…
        dad/
        active.txt      ← name of the active twin

How it stays transparent: persona/memory/voice/media all resolve their root from
``CTWIN_MEMORY_DIR`` (falling back to ``~/.cognitive-twin``). :func:`activate`
sets that env var to the active twin's folder *before* those modules read it, so
they keep working unchanged — they just point at the active twin.

Back-compat: a pre-existing flat ``~/.cognitive-twin/persona.json`` (from before
multi-twin) is adopted once as a twin named ``default`` via :func:`_migrate`, so
nobody loses their existing twin.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path


def _home() -> Path:
    """The shared root (NOT per-twin). Holds the twins/ dir and the shared
    tts-venv. Honors an explicit override only when it doesn't already point
    inside a twin (so activate() is idempotent)."""
    return Path(os.environ.get("CTWIN_HOME", Path.home() / ".cognitive-twin"))


def _twins_dir() -> Path:
    d = _home() / "twins"
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(_home(), stat.S_IRWXU)
    except OSError:
        pass
    return d


def _active_file() -> Path:
    return _twins_dir() / "active.txt"


_SLUG = re.compile(r"[^a-z0-9_-]+")


def slug(name: str) -> str:
    """A safe folder name for a twin: lowercase, spaces→-, junk stripped."""
    s = _SLUG.sub("-", name.strip().lower()).strip("-")
    return s or "twin"


# ---- the registry -------------------------------------------------------------
def list_twins() -> list[str]:
    _migrate()
    return sorted(p.name for p in _twins_dir().iterdir() if p.is_dir())


def exists(name: str) -> bool:
    return (_twins_dir() / slug(name)).is_dir()


def create(name: str, *, make_active: bool = True) -> str:
    """Create a twin folder. Returns its slug. Existing twin is left intact."""
    s = slug(name)
    d = _twins_dir() / s
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, stat.S_IRWXU)
    except OSError:
        pass
    if make_active:
        set_active(s)
    return s


def remove(name: str) -> bool:
    """Delete a twin and all its data. Refuses the active twin unless it's the
    only one left (then it's cleared). Returns True if something was removed."""
    s = slug(name)
    d = _twins_dir() / s
    if not d.is_dir():
        return False
    shutil.rmtree(d, ignore_errors=True)
    if active() == s:
        remaining = list_twins()
        if remaining:
            set_active(remaining[0])
        else:
            try:
                _active_file().unlink()
            except OSError:
                pass
    return True


def active() -> str | None:
    _migrate()
    try:
        if _active_file().is_file():
            name = _active_file().read_text(encoding="utf-8").strip()
            if name and (_twins_dir() / name).is_dir():
                return name
    except OSError:
        pass
    # no valid pointer → fall back to the only twin, if there's exactly one
    twins = [p.name for p in _twins_dir().iterdir() if p.is_dir()]
    if len(twins) == 1:
        set_active(twins[0])
        return twins[0]
    return None


def set_active(name: str) -> str:
    s = slug(name)
    try:
        _active_file().write_text(s, encoding="utf-8")
        os.chmod(_active_file(), stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return s


def active_dir() -> Path | None:
    a = active()
    return (_twins_dir() / a) if a else None


# ---- private flag (a twin that must never be exported/shared) ------------------
# A private twin is personal — e.g. a twin of a specific loved one. The presence
# of a `private.flag` file in the twin folder marks it; sharable-package export
# refuses it. Default is NOT private, so newly created twins can be shared.
_PRIVATE_FLAG = "private.flag"


def is_private(name: str) -> bool:
    d = _twins_dir() / slug(name)
    return (d / _PRIVATE_FLAG).is_file()


def set_private(name: str, private: bool = True) -> bool:
    """Mark/unmark a twin as private. Returns True if the twin exists."""
    d = _twins_dir() / slug(name)
    if not d.is_dir():
        return False
    flag = d / _PRIVATE_FLAG
    try:
        if private:
            flag.write_text("This twin is private and must not be exported.\n",
                            encoding="utf-8")
            os.chmod(flag, stat.S_IRUSR | stat.S_IWUSR)
        elif flag.is_file():
            flag.unlink()
    except OSError:
        pass
    return True


# ---- making the active twin the root other modules read -----------------------
def activate(name: str | None = None) -> Path | None:
    """Point every storage module at the active twin by setting CTWIN_MEMORY_DIR.

    Call once at startup. With a name, switches first. Returns the twin dir, or
    None when no twins exist (callers then use the legacy flat layout)."""
    if name:
        if not exists(name):
            create(name)
        set_active(name)
    d = active_dir()
    if d is not None:
        os.environ["CTWIN_MEMORY_DIR"] = str(d)
        # persona.py prefers CTWIN_PERSONA_DIR; keep it aligned with the twin.
        os.environ["CTWIN_PERSONA_DIR"] = str(d)
    return d


# ---- one-time migration of a pre-multi-twin flat layout -----------------------
_migrated = False


def _migrate() -> None:
    """If the user has flat data (persona.json/memory.jsonl in the home root) and
    no twins yet, adopt it as a twin named 'default'. Idempotent + cheap."""
    global _migrated
    if _migrated:
        return
    _migrated = True
    tdir = _home() / "twins"
    if tdir.is_dir() and any(p.is_dir() for p in tdir.iterdir()):
        return  # already on the multi-twin layout
    flat_markers = ["persona.json", "memory.jsonl", "voice", "voice_samples.txt"]
    has_flat = any((_home() / m).exists() for m in flat_markers)
    if not has_flat:
        return
    dest = tdir / "default"
    dest.mkdir(parents=True, exist_ok=True)
    for m in flat_markers + ["custom_memory.json", "voice_profile.json", "media"]:
        src = _home() / m
        if src.exists():
            try:
                shutil.move(str(src), str(dest / m))
            except OSError:
                pass
    set_active("default")


# ---- status -------------------------------------------------------------------
def status() -> str:
    twins = list_twins()
    if not twins:
        return "twins: none yet — create one with `ctwin twin new \"Name\"`."
    a = active() or "(none)"
    listing = ", ".join((f"*{t}" if t == a else t) for t in twins)
    return f"twins: {listing}   (* = active)   — switch with `ctwin twin use <name>`"


if __name__ == "__main__":
    import sys
    a = sys.argv[1:] if len(sys.argv) > 1 else []
    if a and a[0] == "new" and len(a) > 1:
        print("created + active:", create(" ".join(a[1:])))
    elif a and a[0] == "use" and len(a) > 1:
        print("active:", set_active(" ".join(a[1:])) if exists(" ".join(a[1:])) else "(no such twin)")
    elif a and a[0] == "rm" and len(a) > 1:
        print("removed." if remove(" ".join(a[1:])) else "no such twin.")
    else:
        print(status())
