"""
net — Vera's guarded doorway to the internet.

Vera is on-device by design, so reaching out is a *capability*, not a default.
This module is the ONE place network egress happens, and it's fenced the same
way the amenity booker is:

  * ALLOW-LIST. Only hosts you've allowed are reachable. Nothing else — no
    "download anything". Add hosts with ``allow('example.com')``.
  * PERMISSION MODE (like Claude Code): 'read_only' (fetch text, never save) ·
    'approve' (each fetch/download needs an explicit yes) · 'auto' (allow-listed
    actions run without asking — the opt-in autonomous mode). Default 'approve'.
  * SANDBOX. Downloads only ever land in ``~/.cognitive-twin/downloads/`` with a
    safe, flattened filename. No writing elsewhere.
  * CAPS. Size-limited, timeout-limited, redirect-limited.
  * AUDIT. Every fetch/download is appended to a sealed log — you can always see
    what Vera reached for and when.

No secrets are ever sent; requests carry a plain Vera user-agent. HTTPS only.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import security

# ── config + state (sealed at rest) ───────────────────────────────────────────
_CFG = "net_policy.json"          # {mode, allow: [hosts]}
_LOG = "net_audit.jsonl"          # every reach-out, sealed
_MODES = ("read_only", "approve", "auto")
_MAX_BYTES = 25 * 1024 * 1024     # 25 MB download ceiling
_TIMEOUT = 20
_UA = "Vera/0.1 (on-device personal assistant; +local)"

# A tiny default allow-list of low-risk, useful hosts. Everything else is opt-in.
_DEFAULT_ALLOW = ["pypi.org", "files.pythonhosted.org", "raw.githubusercontent.com",
                  "github.com", "api.github.com", "wikipedia.org", "en.wikipedia.org"]


def _cfg() -> dict[str, Any]:
    d = security.read_state(security.path(_CFG), default=None)
    if not isinstance(d, dict):
        d = {"mode": "approve", "allow": list(_DEFAULT_ALLOW)}
        security.write_state(security.path(_CFG), d)
    return d


def _save(d: dict[str, Any]) -> None:
    security.write_state(security.path(_CFG), d)


def _audit(kind: str, url: str, ok: bool, detail: str = "") -> None:
    security.append_line(security.path(_LOG),
                         {"at": time.time(), "kind": kind, "url": url, "ok": ok, "detail": detail})


# ── policy controls ────────────────────────────────────────────────────────────
def mode() -> str:
    return _cfg().get("mode", "approve")


def set_mode(m: str) -> str:
    m = (m or "").strip().lower()
    if m not in _MODES:
        return f"Mode must be one of: {', '.join(_MODES)}."
    d = _cfg(); d["mode"] = m; _save(d)
    label = {"read_only": "read-only (fetch text, never save)",
             "approve": "approve-each (I ask before every reach-out)",
             "auto": "autonomous (allow-listed reach-outs run without asking)"}[m]
    return f"Network mode set to {label}."


def allow(host: str) -> str:
    host = _host(host)
    if not host:
        return "Give a host like 'example.com'."
    d = _cfg()
    if host in d["allow"]:
        return f"{host} is already allowed."
    d["allow"].append(host); _save(d)
    return f"Allowed {host}. Vera may now reach it (subject to the current mode)."


def disallow(host: str) -> str:
    host = _host(host)
    d = _cfg()
    if host in d["allow"]:
        d["allow"].remove(host); _save(d)
        return f"Removed {host} from the allow-list."
    return f"{host} wasn't on the allow-list."


def policy() -> str:
    d = _cfg()
    return (f"Network: mode = {d['mode']}. Allowed hosts ({len(d['allow'])}): "
            + ", ".join(sorted(d["allow"])) + ".")


# ── the gate ───────────────────────────────────────────────────────────────────
def _host(u: str) -> str:
    u = (u or "").strip().lower()
    if "://" in u:
        u = urlparse(u).netloc
    return u.split("/")[0].split(":")[0]


def _allowed(url: str) -> tuple[bool, str]:
    p = urlparse(url)
    if p.scheme != "https":
        return False, "only https URLs are allowed"
    host = p.netloc.lower().split(":")[0]
    allow = _cfg()["allow"]
    ok = any(host == a or host.endswith("." + a) for a in allow)
    return (ok, "" if ok else f"{host} is not on the allow-list (add it with net allow {host})")


def _check(url: str, *, approved: bool, saving: bool) -> str | None:
    """Return an error/permission string if the reach-out must NOT proceed, else
    None. Encodes the permission mode."""
    ok, why = _allowed(url)
    if not ok:
        _audit("blocked", url, False, why)
        return f"[blocked] {why}"
    m = mode()
    if saving and m == "read_only":
        return "[blocked] read-only mode won't save downloads. Switch to approve/auto."
    if m == "approve" and not approved:
        return ("[needs approval] I can reach this, but you're in approve-each mode. "
                "Confirm this fetch/download to proceed.")
    return None  # read_only fetch, or approve+approved, or auto → go


def fetch_text(url: str, *, approved: bool = False, max_chars: int = 20000) -> str:
    """Fetch a page/text from an allowed host. Read-only (never saves). Returns
    the text (trimmed) or a clear status string."""
    blk = _check(url, approved=approved, saving=False)
    if blk:
        return blk
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            raw = r.read(_MAX_BYTES + 1)
        text = raw.decode("utf-8", "replace")
        # crude tag strip so a page reads as text for the model
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        _audit("fetch", url, True, f"{len(text)} chars")
        return text[:max_chars] + ("…[trimmed]" if len(text) > max_chars else "")
    except (urllib.error.URLError, OSError, ValueError) as e:
        _audit("fetch", url, False, str(e))
        return f"[error] couldn't fetch: {e}"


def download(url: str, *, approved: bool = False) -> str:
    """Download a file from an allowed host into the sandbox. Needs approval
    unless in 'auto' mode. Returns where it landed, or a status string."""
    blk = _check(url, approved=approved, saving=True)
    if blk:
        return blk
    name = _safe_name(url)
    dest_dir = security.home() / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = r.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            _audit("download", url, False, "exceeds size cap")
            return f"[blocked] file exceeds the {_MAX_BYTES // (1024*1024)} MB safety cap."
        dest.write_bytes(data)
        try:
            dest.chmod(0o600)
        except OSError:
            pass
        _audit("download", url, True, f"{len(data)} bytes → {dest}")
        return f"Downloaded {len(data):,} bytes → {dest} (sandbox)."
    except (urllib.error.URLError, OSError, ValueError) as e:
        _audit("download", url, False, str(e))
        return f"[error] download failed: {e}"


def _safe_name(url: str) -> str:
    base = os.path.basename(urlparse(url).path) or "download"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:80]
    return base or "download"


def recent_activity(n: int = 15) -> str:
    """What Vera has reached for lately — the audit trail, readable."""
    rows = security.read_lines(security.path(_LOG))
    if not rows:
        return "Vera hasn't reached the internet yet."
    rows = rows[-n:]
    out = ["Recent network activity (sealed audit):"]
    for r in reversed(rows):
        t = time.strftime("%m-%d %H:%M", time.localtime(r.get("at", 0)))
        mark = "✓" if r.get("ok") else "✗"
        out.append(f"  {mark} {t} {r.get('kind','')}: {r.get('url','')[:60]}  {r.get('detail','')}")
    return "\n".join(out)
