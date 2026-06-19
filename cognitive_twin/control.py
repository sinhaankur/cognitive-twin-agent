"""
Screen control — opt-in, permissioned, safe-by-default.

Lets the twin *see* the screen and take a small set of *safe* actions (open an
app, open a URL, run an allow-listed Shortcut). It deliberately does NOT do blind
mouse/keyboard control — an LLM driving the cursor is how things get broken.

Safety model:
  1. OFF by default. Nothing here works unless the user opts in
     (env CTWIN_CONTROL=1, or enable() at runtime).
  2. Read actions (see the screen) never change anything.
  3. Mutating actions (open app/url/shortcut) go through a confirmation hook —
     the caller decides how to confirm (the CLI prompts y/N). Deny = nothing runs.
  4. No arbitrary shell. Apps/URLs/shortcuts are passed as arguments to specific
     binaries (open / osascript), never interpolated into a shell string.

macOS only. Reading on-screen text needs Accessibility permission; the user
grants it in System Settings the first time.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Callable


# ---- opt-in gate --------------------------------------------------------------
_enabled = os.environ.get("CTWIN_CONTROL", "").strip() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    return _enabled


def enable(on: bool = True) -> None:
    """Turn screen control on/off at runtime (the kill switch)."""
    global _enabled
    _enabled = on


# Confirmation hook for mutating actions. Default: deny (safe). The CLI replaces
# this with an interactive y/N prompt; a GUI would show a dialog.
ConfirmFn = Callable[[str], bool]
_confirm: ConfirmFn = lambda _action: False


def set_confirm(fn: ConfirmFn) -> None:
    global _confirm
    _confirm = fn


class ControlDenied(Exception):
    pass


def _require_enabled() -> str | None:
    if not _enabled:
        return ("[control disabled] Screen control is off. Enable it explicitly "
                "(set CTWIN_CONTROL=1) — it's off by default for safety.")
    if sys.platform != "darwin":
        return "[control unavailable] Screen control is macOS-only."
    return None


def _osascript(script: str, timeout: float = 8.0) -> str:
    """Run an AppleScript snippet, return stdout (or a clear error string)."""
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return f"[error] {r.stderr.strip() or 'osascript failed'}"
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] {e}"


# ---- READ actions (no confirmation; never change anything) --------------------
def current_app() -> str:
    if (err := _require_enabled()):
        return err
    name = _osascript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    )
    return f"Frontmost app: {name}" if name and not name.startswith("[") else name


def list_windows() -> str:
    if (err := _require_enabled()):
        return err
    out = _osascript(
        'tell application "System Events" to get name of every window of '
        '(first application process whose frontmost is true)'
    )
    if out.startswith("["):
        return out
    wins = [w.strip() for w in out.split(",") if w.strip()]
    return ("Open windows (frontmost app): " + "; ".join(wins)) if wins else "No titled windows."


def read_screen_text(max_chars: int = 1200) -> str:
    """Read visible text of the frontmost window via the Accessibility tree.
    Requires Accessibility permission; returns guidance if it's not granted."""
    if (err := _require_enabled()):
        return err
    script = (
        'tell application "System Events"\n'
        '  set p to first application process whose frontmost is true\n'
        '  try\n'
        '    set t to value of attribute "AXTitle" of p\n'
        '  end try\n'
        '  set out to ""\n'
        '  try\n'
        '    set els to entire contents of front window of p\n'
        '    repeat with e in els\n'
        '      try\n'
        '        set v to value of e\n'
        '        if v is not missing value and (class of v) is text and (length of v) > 0 then\n'
        '          set out to out & v & " | "\n'
        '        end if\n'
        '      end try\n'
        '    end repeat\n'
        '  end try\n'
        '  return out\n'
        'end tell'
    )
    out = _osascript(script, timeout=12.0)
    if out.startswith("[error]"):
        return (out + "  (If this mentions permissions, grant Accessibility to your "
                "terminal/app in System Settings → Privacy & Security → Accessibility.)")
    out = out.strip()
    if not out:
        return "[no readable text] The frontmost window exposed no text via Accessibility."
    return out[:max_chars] + ("…[truncated]" if len(out) > max_chars else "")


# ---- SAFE actions (confirmation-gated) ----------------------------------------
_APP_NAME = re.compile(r"^[\w .&'\-]{1,60}$")           # plain app names only
_URL = re.compile(r"^https?://[^\s]{1,300}$", re.IGNORECASE)
_SHORTCUT = re.compile(r"^[\w .&'\-]{1,80}$")


def open_app(name: str) -> str:
    if (err := _require_enabled()):
        return err
    name = name.strip()
    if not _APP_NAME.match(name):
        return f"[refused] '{name}' isn't a plain app name."
    if not _confirm(f"Open the app “{name}”?"):
        return f"[cancelled] Did not open {name}."
    try:
        subprocess.run(["open", "-a", name], capture_output=True, text=True, timeout=8)
        return f"Opened {name}."
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] {e}"


def open_url(url: str) -> str:
    if (err := _require_enabled()):
        return err
    url = url.strip()
    if not _URL.match(url):
        return "[refused] Only http(s) URLs are allowed."
    if not _confirm(f"Open this URL in your browser?\n  {url}"):
        return "[cancelled] Did not open the URL."
    try:
        subprocess.run(["open", url], capture_output=True, text=True, timeout=8)
        return f"Opened {url}"
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] {e}"


def run_shortcut(name: str) -> str:
    """Run a macOS Shortcut by name (Shortcuts.app). The user authors these, so
    they're a safe, user-controlled way to extend what the twin can do."""
    if (err := _require_enabled()):
        return err
    name = name.strip()
    if not _SHORTCUT.match(name):
        return f"[refused] '{name}' isn't a valid shortcut name."
    if not _confirm(f"Run the Shortcut “{name}”?"):
        return f"[cancelled] Did not run {name}."
    try:
        r = subprocess.run(["shortcuts", "run", name],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return f"[error] {r.stderr.strip() or 'shortcut failed'}"
        return f"Ran shortcut “{name}”. {r.stdout.strip()}".strip()
    except FileNotFoundError:
        return "[unavailable] The `shortcuts` CLI isn't available on this macOS."
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] {e}"


def status() -> str:
    if not _enabled:
        return "screen control: OFF (safe default). Enable with CTWIN_CONTROL=1."
    return "screen control: ON — read + safe actions (open app/url/shortcut), each confirmed."
