"""
site_patrol — Vera watches sinhaankur.com and, when you hand her the switch,
fixes it.

Ankur's ask, in his words: Vera stays connected to the website, keeps checking
what's a bug, "takes care of things", and can "take control" to fix + push — but
only "when I switch it on and off". So control is a *switch he holds*:

  • WATCH is always safe. Vera fetches the live site + key routes read-only,
    checks each for HTTP errors / blank / error pages, and logs what she finds
    through the security kernel. She never changes anything in this mode.

  • CONTROL is a toggle YOU own (CTWIN_SITE_CONTROL=1, or take_control(True) at
    runtime; flip it off and she drops straight back to watch-only). ONLY while
    it's on may she act on a bug: run the repo's own build + smoke test and — if
    and ONLY IF the smoke test passes — commit and push to `origin`, which
    publishes via GitHub Pages to www.sinhaankur.com.

The one floor that is NOT negotiable, even with control on: she pushes a fix only
if `pnpm test:site` is green. Pushing broken code to a live site is the opposite
of "taking care of it", so a failing smoke test refuses the push and reports.

This deliberately mirrors control.py (opt-in gate + hard allow-list + no arbitrary
shell — every action is a fixed argv to a known binary) and net.py (sealed audit
of every reach-out). It logs through security.py so `security doctor` stays whole.

  CLI:  python3 -m cognitive_twin.site_patrol status
        python3 -m cognitive_twin.site_patrol check              # one watch pass
        python3 -m cognitive_twin.site_patrol watch [--interval 300] [--minutes 0]
        python3 -m cognitive_twin.site_patrol control on|off     # the switch
        python3 -m cognitive_twin.site_patrol log [-n 20]

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import security

# ── what Vera watches ──────────────────────────────────────────────────────────
SITE = "https://www.sinhaankur.com"
# A representative slice — the home hero, the heavy engines, and a plain page.
# Kept small so a pass is cheap; extend if a route starts mattering.
ROUTES = ["/", "/lab", "/lab/celestial", "/waves", "/skills", "/about"]

# The local checkout the fixes are built + pushed from. The site lives at the
# repo root (see its CLAUDE.md), not a subfolder.
REPO = Path(os.environ.get("CTWIN_SITE_REPO",
                           Path.home() / "Documents" / "Portfolio"))

_LOG = "site_patrol.jsonl"          # every pass + every action, sealed
_UA = "Vera-SitePatrol/0.1 (+local; on-device)"
_TIMEOUT = 25


# ── the switch (control is off by default; you hold it) ─────────────────────────
_control = os.environ.get("CTWIN_SITE_CONTROL", "").strip() in {"1", "true", "yes", "on"}


def has_control() -> bool:
    return _control


def take_control(on: bool = True) -> str:
    """Flip the control switch. ON lets Vera fix + push (green smoke only); OFF
    drops her back to watch-only. This is the thing Ankur turns on and off."""
    global _control
    _control = on
    _audit("control", ok=True, detail=f"switched {'ON' if on else 'OFF'}")
    if on:
        return ("Control ON — I may now fix a bug and push it live, but only if "
                "the smoke test passes. Flip it off any time and I go back to "
                "just watching.")
    return "Control OFF — watching only. I won't change anything until you switch it back on."


# ── sealed audit (through the kernel, like net.py) ─────────────────────────────
def _audit(kind: str, *, ok: bool, detail: str = "", route: str = "") -> None:
    security.append_line(security.path(_LOG), {
        "at": time.time(), "kind": kind, "ok": ok, "route": route, "detail": detail,
    })


# ── WATCH: read-only health of the live site ───────────────────────────────────
def _fetch(url: str) -> tuple[int, str]:
    """GET a URL. Returns (status, body-or-error). Read-only; no cookies, no
    secrets — a plain Vera user-agent."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            body = r.read(200_000).decode("utf-8", "replace")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, f"[http {e.code}] {e.reason}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, f"[unreachable] {e}"


def _looks_broken(status: int, body: str) -> str | None:
    """Heuristics for a bad page from the outside: bad status, blank shell, or a
    telltale error string. Returns a reason if broken, else None."""
    if status == 0:
        return body  # unreachable / network error text
    if status >= 400:
        return f"HTTP {status}"
    stripped = body.strip()
    if len(stripped) < 400:
        return "near-blank page (body under 400 bytes)"
    low = body.lower()
    for marker in ("application error", "internal server error",
                   "you need to enable javascript" ):
        if marker in low:
            return f"error marker on page: “{marker}”"
    # A Next.js page always carries its runtime markers (the __next app root,
    # __NEXT_DATA__, or the _next/static chunk graph). Full-screen experiences
    # (/waves, /sky) legitimately have no <main>, so don't require one — only a
    # total absence of every Next marker means a genuinely broken export.
    if "__next" not in low and "__next_data__" not in low and "/_next/" not in body:
        return "no Next.js runtime markers — export may be broken"
    return None


def check_once() -> dict:
    """One read-only pass over the watched routes. Returns a report dict with any
    problems found. Never changes anything."""
    problems: list[dict] = []
    for route in ROUTES:
        url = SITE + route
        status, body = _fetch(url)
        reason = _looks_broken(status, body)
        ok = reason is None
        _audit("check", ok=ok, route=route, detail=(reason or f"HTTP {status} ok"))
        if not ok:
            problems.append({"route": route, "status": status, "reason": reason})
    return {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "checked": len(ROUTES),
        "problems": problems,
        "healthy": not problems,
    }


# ── CONTROL: build + smoke + push (only with the switch on, only if green) ──────
def _run(argv: list[str], *, timeout: int) -> tuple[bool, str]:
    """Run a fixed argv in the repo. No shell string, ever — same discipline as
    control.py. Returns (ok, tail-of-output)."""
    try:
        r = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                           timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out[-2000:]
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"[error running {argv[0]}] {e}"


def verify_local() -> tuple[bool, str]:
    """Build the site and run its own full-route smoke test the way its docs
    prescribe. Green here is the gate for any push."""
    if not (REPO / "package.json").is_file():
        return False, f"no checkout at {REPO} (set CTWIN_SITE_REPO)"
    ok, out = _run(["pnpm", "build"], timeout=600)
    if not ok:
        return False, "build failed:\n" + out
    # serve out/ + smoke. pnpm test:site expects the static server on :8899.
    subprocess.run(["pkill", "-f", "http.server 8899"], capture_output=True)
    server = subprocess.Popen(["python3", "-m", "http.server", "8899"],
                              cwd=str(REPO / "out"),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(2)
        ok, out = _run(["pnpm", "test:site"], timeout=600)
    finally:
        server.terminate()
        subprocess.run(["pkill", "-f", "http.server 8899"], capture_output=True)
    return (ok, "smoke test green" if ok else "smoke test FAILED:\n" + out)


def _dirty() -> bool:
    r = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def push_fix(message: str) -> str:
    """Commit the working tree and push to origin — publishing to the live site.
    Refuses unless (a) the control switch is on and (b) the smoke test is green.
    No Co-Authored-By (the repo enforces a single author)."""
    if not _control:
        _audit("push", ok=False, detail="refused: control switch is OFF")
        return ("[refused] Control is off. Flip the switch on (control on) before I "
                "change the live site.")
    if not _dirty():
        return "[nothing to push] The working tree is clean — no fix to ship."

    ok, detail = verify_local()
    if not ok:
        _audit("push", ok=False, detail="refused: " + detail.split(chr(10))[0])
        return ("[refused] I will NOT push a red build to the live site.\n" + detail)

    # Stage only tracked changes + new files the fix added; commit; push origin.
    steps = [
        ["git", "-C", str(REPO), "add", "-A"],
        ["git", "-C", str(REPO), "commit", "-m", message],
        ["git", "-C", str(REPO), "push", "origin", "HEAD"],
    ]
    for argv in steps:
        good, out = _run(argv, timeout=120)
        if not good:
            _audit("push", ok=False, detail=f"{argv[2]} failed: {out[-200:]}")
            return f"[error] `{' '.join(argv[1:4])}` failed:\n{out}"
    _audit("push", ok=True, detail=message)
    return ("Pushed to origin — the fix is live (GitHub Pages will publish it in a "
            "minute or two). Smoke was green before it went.")


# ── watch loop ─────────────────────────────────────────────────────────────────
def watch(*, interval: float = 300.0, minutes: float = 0.0) -> int:
    """Poll the live site every `interval` seconds until the time budget is spent
    or Ctrl-C. Reports problems; with the control switch ON, it still only *acts*
    when you wire an explicit fix — watch never edits code by itself. Returns the
    number of passes that found a problem."""
    print(f"Site patrol — watching {SITE} every {int(interval)}s.")
    print(f"Control: {'ON (may fix + push on green)' if _control else 'OFF (watching only)'}.")
    print("Ctrl-C to stop.\n")
    deadline = time.time() + minutes * 60 if minutes and minutes > 0 else None
    bad_passes = 0
    try:
        while True:
            rep = check_once()
            if rep["healthy"]:
                print(f"  · {rep['at']}  ✓ all {rep['checked']} route(s) healthy")
            else:
                bad_passes += 1
                print(f"  · {rep['at']}  ✗ {len(rep['problems'])} problem(s):")
                for p in rep["problems"]:
                    print(f"      {p['route']}  →  {p['reason']}")
                print("    (a real page bug is Ankur's to fix or approve; I flag "
                      "it and log it — I don't guess a patch to a live site.)")
            if deadline and time.time() >= deadline:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return bad_passes


def status() -> str:
    where = REPO if (REPO / "package.json").is_file() else f"{REPO} (not found)"
    return (f"Site patrol\n"
            f"  target : {SITE}\n"
            f"  routes : {', '.join(ROUTES)}\n"
            f"  repo   : {where}\n"
            f"  control: {'ON — may fix + push (green smoke only)' if _control else 'OFF — watching only'}")


def recent(n: int = 20) -> str:
    rows = security.read_lines(security.path(_LOG))
    if not rows:
        return "No patrol activity logged yet."
    rows = rows[-n:]
    out = ["Recent site-patrol activity (sealed):"]
    for r in reversed(rows):
        t = time.strftime("%m-%d %H:%M", time.localtime(r.get("at", 0)))
        mark = "✓" if r.get("ok") else "✗"
        route = r.get("route", "")
        out.append(f"  {mark} {t} {r.get('kind',''):<8} {route:<16} {r.get('detail','')}")
    return "\n".join(out)


# ── CLI ────────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    if cmd == "status":
        print(status()); return 0
    if cmd == "check":
        rep = check_once()
        if rep["healthy"]:
            print(f"✓ all {rep['checked']} route(s) healthy ({rep['at']}).")
        else:
            print(f"✗ {len(rep['problems'])} problem(s) ({rep['at']}):")
            for p in rep["problems"]:
                print(f"    {p['route']}  →  {p['reason']}")
        return 0 if rep["healthy"] else 1
    if cmd == "watch":
        interval, minutes = 300.0, 0.0
        i = 0
        while i < len(rest):
            if rest[i] == "--interval" and i + 1 < len(rest):
                interval = float(rest[i + 1]); i += 2
            elif rest[i] == "--minutes" and i + 1 < len(rest):
                minutes = float(rest[i + 1]); i += 2
            else:
                i += 1
        watch(interval=interval, minutes=minutes); return 0
    if cmd == "control":
        if rest and rest[0] in {"on", "off"}:
            print(take_control(rest[0] == "on")); return 0
        print("usage: control on|off"); return 2
    if cmd == "log":
        n = 20
        if "-n" in rest:
            try:
                n = int(rest[rest.index("-n") + 1])
            except (IndexError, ValueError):
                pass
        print(recent(n)); return 0

    print(f"unknown command: {cmd}\n"); print(__doc__); return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
