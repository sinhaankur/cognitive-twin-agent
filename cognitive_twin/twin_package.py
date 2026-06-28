"""
Sharable twin packages — export a twin's *identity* so a loved one can import it.

A ``.twin`` file is a small zip holding only what makes the twin *them*:
  - ``persona.json``        — who they are (name, traits, likes, values, style…)
  - ``voice/reference.wav`` — the cloning reference (their actual voice), if set
  - ``voice/voice_clone.json`` — engine meta for the reference
  - ``twin.manifest.json`` — what's inside + a format version

Deliberately **excluded** (private, never travels): behavioral memory
(``memory.jsonl``), custom remembered facts, distilled writing-style samples
(``voice_profile.json`` / ``voice_samples.txt``), captured ``media/``, the
enable flag, and all the scratch A/B render files. Sharing a twin shares an
*identity*, not someone's private history.

This builds on the per-twin layout (see :mod:`cognitive_twin.twins`): export
reads a twin's folder, import creates a new twin from the package.

Local + explicit: nothing is uploaded; the user moves the ``.twin`` file
themselves. Import always lands in a fresh, named twin so it can't clobber an
existing one.
"""

from __future__ import annotations

import json
import os
import stat
import zipfile
from pathlib import Path

from . import twins

MANIFEST = "twin.manifest.json"
FORMAT_VERSION = 1

# Exactly what may travel in a package. Anything not listed is never exported and
# is ignored on import — a conservative allow-list, not a deny-list.
SHAREABLE = [
    "persona.json",
    "voice/reference.wav",
    "voice/voice_clone.json",
]


def _twin_dir(name: str) -> Path | None:
    d = twins._twins_dir() / twins.slug(name)
    return d if d.is_dir() else None


# ---- export -------------------------------------------------------------------
def export_twin(name: str, out_path: str) -> dict:
    """Write a ``.twin`` package for ``name`` to ``out_path``. Returns a status
    dict. Only the shareable allow-list is included; private data never is."""
    src = _twin_dir(name)
    if src is None:
        return {"ok": False, "error": f"no twin named '{name}'"}

    # Hard refusal: a twin marked private (e.g. a specific loved one) is never
    # exportable. This is the boundary that keeps a personal twin on this machine.
    if twins.is_private(name):
        return {"ok": False, "error": f"twin '{name}' is private and cannot be "
                f"exported. (Unmark with `ctwin twin unprivate {name}` only if you "
                f"truly intend to share it.)"}

    persona_file = src / "persona.json"
    if not persona_file.is_file():
        return {"ok": False, "error": f"twin '{name}' has no persona to share"}

    out = Path(out_path).expanduser()
    if out.suffix != ".twin":
        out = out.with_suffix(".twin")

    # read the persona to record a friendly display name in the manifest
    try:
        persona_data = json.loads(persona_file.read_text(encoding="utf-8"))
        display = persona_data.get("name") or twins.slug(name)
    except (OSError, json.JSONDecodeError):
        display = twins.slug(name)

    included: list[str] = []
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in SHAREABLE:
                p = src / rel
                if p.is_file():
                    z.write(p, rel)
                    included.append(rel)
            manifest = {
                "format": FORMAT_VERSION,
                "kind": "cognitive-twin-package",
                "display_name": display,
                "includes": included,
                "has_voice": "voice/reference.wav" in included,
                "note": "persona + cloned-voice reference only — no private memory.",
            }
            z.writestr(MANIFEST, json.dumps(manifest, indent=2))
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "path": str(out), "display_name": display,
            "included": included, "has_voice": manifest["has_voice"]}


# ---- import -------------------------------------------------------------------
def inspect_package(pkg_path: str) -> dict:
    """Read a package's manifest without importing it (so the user can preview)."""
    p = Path(pkg_path).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"file not found: {pkg_path}"}
    try:
        with zipfile.ZipFile(p) as z:
            if MANIFEST not in z.namelist():
                return {"ok": False, "error": "not a twin package (no manifest)"}
            manifest = json.loads(z.read(MANIFEST).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"unreadable package: {e}"}
    if manifest.get("kind") != "cognitive-twin-package":
        return {"ok": False, "error": "not a cognitive-twin package"}
    return {"ok": True, **manifest}


def import_twin(pkg_path: str, *, name: str | None = None,
                make_active: bool = True) -> dict:
    """Create a NEW twin from a package. ``name`` overrides the package's display
    name; a clash is avoided by suffixing. Never overwrites an existing twin."""
    info = inspect_package(pkg_path)
    if not info.get("ok"):
        return info

    wanted = name or info.get("display_name") or "imported-twin"
    target = twins.slug(wanted)
    # don't clobber: if the slug exists, suffix -2, -3, …
    if twins.exists(target):
        i = 2
        while twins.exists(f"{target}-{i}"):
            i += 1
        target = f"{target}-{i}"

    twin_slug = twins.create(target, make_active=make_active)
    dest = twins._twins_dir() / twin_slug

    p = Path(pkg_path).expanduser()
    extracted: list[str] = []
    try:
        with zipfile.ZipFile(p) as z:
            for rel in SHAREABLE:  # allow-list only — ignore anything unexpected
                if rel in z.namelist():
                    out = dest / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(z.read(rel))
                    try:
                        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
                    except OSError:
                        pass
                    extracted.append(rel)
    except (OSError, zipfile.BadZipFile) as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "twin": twin_slug, "active": make_active,
            "imported": extracted, "has_voice": "voice/reference.wav" in extracted}


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "export":
        print(json.dumps(export_twin(a[1], a[2]), indent=2))
    elif len(a) >= 2 and a[0] == "import":
        print(json.dumps(import_twin(a[1], name=a[2] if len(a) > 2 else None), indent=2))
    elif len(a) >= 2 and a[0] == "inspect":
        print(json.dumps(inspect_package(a[1]), indent=2))
    else:
        print("usage: twin_package.py export <twin> <out.twin> | "
              "import <file.twin> [name] | inspect <file.twin>")
