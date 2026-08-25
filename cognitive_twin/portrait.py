"""
portrait.py — a loved one, held in 3D (opt-in, on-device).

The "living photo": you choose a photo, and Vera builds a gentle 3D likeness that
lives inside the orb — a face you can watch turn in the light. This is the honest
opposite of a deepfake: no geometry is invented. A local depth model estimates how
far each pixel sits from the camera, and Blender displaces a mesh by that depth and
projects the *actual photo* onto it. It is the person's own image, given relief.

Unlike the Photos sense (photos.py — metadata only, "never pixels"), this one reads
the chosen photo's pixels. So it is its OWN switch, with its own plain-spoken
consent in the app ("this reads the photo itself; built and kept on this Mac").

Honesty / safety rules, matching the rest of her mind:
  - Opt-in only. Nothing here runs unless the user turns "See a loved one in 3D"
    on AND hands over a specific photo. One photo, chosen deliberately.
  - Local only. The depth model runs on-device; Blender runs on-device; the output
    USDZ is written under the app's Application Support. No network code here.
  - Transparent. Every build writes a provenance sidecar (source image, model,
    when) next to the mesh, and returns it, so the app can show where the face
    came from. Turn the switch off and the face is gone from the orb.
  - Owner-only files (0700 dir / 0600 sidecar), like memory and the day ledger.

The heavy lifting lives in scripts/portrait3d/ (depth.py + the Blender builder),
run in an isolated venv so the depth model never touches the system Python. This
module is the thin, honest orchestrator the server calls.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any

# where the pipeline lives (isolated venv + stages)
_PIPE = Path(__file__).resolve().parent.parent / "scripts" / "portrait3d"
_VENV_PY = _PIPE / ".venv" / "bin" / "python"


def _blender() -> str | None:
    """Locate Blender across platforms: PATH first (Linux/Windows/brew), then the
    macOS app bundle, then common install spots. Returns None if not found so
    callers can degrade gracefully instead of assuming a macOS path."""
    onpath = shutil.which("blender") or shutil.which("Blender")
    if onpath:
        return onpath
    candidates = [
        "/Applications/Blender.app/Contents/MacOS/Blender",             # macOS
        str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
        "/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender",  # Linux
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",      # Windows
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _out_dir() -> Path:
    """Where the app looks for the face, owner-only. Uses macOS Application Support
    when present; falls back to the shared on-device state dir on other platforms so
    this never crashes off-Mac (portrait rendering itself is macOS-only, but the path
    resolution must stay safe everywhere)."""
    mac_support = Path.home() / "Library" / "Application Support"
    base = (mac_support if mac_support.is_dir()
            else Path.home() / ".cognitive-twin") / "Vera" / "portrait"
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, stat.S_IRWXU)  # 0700 — fail soft on Windows
    except OSError:
        pass
    return base


def _secure(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


def status() -> dict[str, Any]:
    """What the app needs to reason about the sense, without assuming."""
    out = _out_dir()
    mesh = out / "face.usdz"
    prov = out / "provenance.json"
    ready = mesh.exists()
    info: dict[str, Any] = {
        "ready": ready,
        "mesh": str(mesh) if ready else None,
        "pipeline_installed": _VENV_PY.exists(),
        "blender_present": _blender() is not None,
    }
    if prov.exists():
        try:
            info["provenance"] = json.loads(prov.read_text())
        except (ValueError, OSError):
            pass
    return info


def clear() -> dict[str, Any]:
    """Forget the face — the switch off / 'remove' path. Leaves the orb normal."""
    out = _out_dir()
    for name in ("face.usdz", "depth.png", "depth_preview.png", "provenance.json", "source.png"):
        p = out / name
        if p.exists():
            p.unlink()
    return {"ok": True, "ready": False}


def build(image_path: str) -> dict[str, Any]:
    """Build the 3D likeness from one chosen photo. Returns provenance + mesh path.

    Deterministic, honest failure: if the pipeline isn't installed or Blender is
    missing, say so plainly rather than half-building something the orb would then
    try to animate.
    """
    src = Path(image_path).expanduser()
    if not src.exists():
        return {"ok": False, "error": "photo not found"}
    if not _VENV_PY.exists():
        return {"ok": False, "error": "depth pipeline not installed"}
    blender = _blender()
    if blender is None:
        return {"ok": False, "error": "Blender not found"}

    out = _out_dir()
    # keep our own copy of the source so the face survives the original moving/being deleted
    kept = out / "source.png"
    shutil.copyfile(src, kept)
    _secure(kept)

    depth = out / "depth.png"
    mesh = out / "face.usdz"

    # 1) depth — isolated venv, on-device
    d = subprocess.run(
        [str(_VENV_PY), str(_PIPE / "depth.py"), str(kept), str(depth)],
        capture_output=True, text=True,
    )
    if d.returncode != 0 or not depth.exists():
        return {"ok": False, "error": "depth estimation failed", "detail": d.stderr[-800:]}

    # 2) relief + texture + USDZ export — Blender, headless
    b = subprocess.run(
        [blender, "--background", "--python", str(_PIPE / "build_face.py"),
         "--", str(kept), str(depth), str(mesh)],
        capture_output=True, text=True,
    )
    if b.returncode != 0 or not mesh.exists():
        return {"ok": False, "error": "Blender build failed", "detail": b.stdout[-800:] + b.stderr[-400:]}

    _secure(mesh)
    prov = {
        "source": str(src),
        "built": _dt.datetime.now().isoformat(timespec="seconds"),
        "depth_model": "Depth-Anything-V2-Small (on-device)",
        "note": "3D relief from the photo's own pixels; no geometry invented.",
    }
    provfile = out / "provenance.json"
    provfile.write_text(json.dumps(prov, indent=2))
    _secure(provfile)
    return {"ok": True, "ready": True, "mesh": str(mesh), "provenance": prov}
