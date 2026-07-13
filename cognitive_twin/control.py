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


# ---- screenshot + on-device OCR (read-only) -----------------------------------
# The Accessibility tree (read_screen_text) misses text that apps draw as pixels
# — a browser <canvas>, a video frame, VS Code's editor, an image. For those we
# take an actual screenshot and OCR it with Apple's Vision framework, entirely
# on-device: no cloud, no LLM. The PNG is written to a temp file the caller can
# keep or discard.

# A tiny Swift program that OCRs an image path with Vision and prints the text.
# Compiled on first use with `swiftc`; cached so we don't rebuild every call.
_OCR_SWIFT = r'''
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1, let img = NSImage(contentsOfFile: args[1]),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("could not load image\n".data(using: .utf8)!)
    exit(2)
}
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = true
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([req])
    let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    print(lines.joined(separator: "\n"))
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(3)
}
'''


def _ocr_binary_path() -> str:
    """Path to the cached compiled OCR helper (built on first use)."""
    import tempfile
    return os.path.join(tempfile.gettempdir(), "ctwin_vision_ocr")


def _ensure_ocr_binary() -> str | None:
    """Compile the Swift OCR helper if needed. Returns its path, or None if the
    Swift toolchain isn't available (caller then reports the PNG-only result)."""
    binpath = _ocr_binary_path()
    if os.path.exists(binpath):
        return binpath
    import shutil
    import tempfile
    if not shutil.which("swiftc"):
        return None
    src = os.path.join(tempfile.gettempdir(), "ctwin_vision_ocr.swift")
    try:
        with open(src, "w") as f:
            f.write(_OCR_SWIFT)
        r = subprocess.run(["swiftc", "-O", src, "-o", binpath],
                           capture_output=True, text=True, timeout=90)
        return binpath if r.returncode == 0 and os.path.exists(binpath) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _frontmost_window_id() -> str | None:
    """CGWindowID of the frontmost app's front window, for `screencapture -l`.
    Best-effort; None if it can't be determined (many apps, e.g. Chromium-based
    browsers, don't expose AXWindowNumber — caller then falls back to full screen)."""
    out = _osascript(
        'tell application "System Events" to get value of attribute "AXWindowNumber" '
        'of front window of (first application process whose frontmost is true)'
    )
    out = out.strip()
    return out if out.isdigit() else None


def capture_screen(scope: str = "window", ocr: bool = True, max_chars: int = 4000) -> str:
    """Screenshot the front window (scope="window") or the whole display
    (scope="full"), then optionally OCR it on-device with Vision.

    Read-only: it captures pixels, never changes anything. Returns the OCR text
    (plus the saved PNG path), or just the path if OCR isn't available.
    Needs Screen Recording permission the first time (macOS prompts).
    """
    if (err := _require_enabled()):
        return err
    if scope not in {"window", "full"}:
        return f"[refused] scope must be 'window' or 'full', got '{scope}'."

    import tempfile
    png = os.path.join(tempfile.gettempdir(),
                       f"ctwin_screen_{os.getpid()}.png")

    # -x: silent (no shutter sound/UI). -o: omit window shadow.
    cmd = ["screencapture", "-x"]
    fell_back = False
    if scope == "window":
        wid = _frontmost_window_id()
        if wid:
            cmd += ["-o", "-l", wid]
        else:
            scope = "full"  # couldn't resolve a window; grab the display instead
            fell_back = True
    cmd.append(png)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] screencapture failed: {e}"
    if r.returncode != 0 or not os.path.exists(png):
        msg = r.stderr.strip() or "screencapture produced no image"
        return (f"[error] {msg}  (If this mentions permission, grant Screen "
                "Recording to your terminal/app in System Settings → Privacy & "
                "Security → Screen Recording, then retry.)")

    header = f"[screenshot: {scope}] saved to {png}"
    if fell_back:
        header += "  (front window id wasn't exposed by the app — captured the "
        header += "full display instead)"
    if not ocr:
        return header

    ocr_bin = _ensure_ocr_binary()
    if ocr_bin is None:
        return (header + "\n[ocr unavailable] The Swift/Vision toolchain wasn't "
                "found, so no text was extracted. Install Xcode command-line tools "
                "(`xcode-select --install`) to enable on-device OCR.")
    try:
        r = subprocess.run([ocr_bin, png], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return header + f"\n[ocr error] {e}"
    if r.returncode != 0:
        return header + f"\n[ocr error] {r.stderr.strip() or 'Vision OCR failed'}"

    text = r.stdout.strip()
    if not text:
        return header + "\n[no text found] Vision OCR read no text in the image."
    clipped = text[:max_chars] + ("…[truncated]" if len(text) > max_chars else "")
    return header + "\n--- on-screen text (Vision OCR) ---\n" + clipped


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


# ---- CLI ----------------------------------------------------------------------
def _main(argv: list[str]) -> int:
    """Direct CLI for the read-only screen actions, so you can run them without
    the twin:  python3 -m cognitive_twin.control <command>

    Commands:
      app                     print the frontmost app
      windows                 list the frontmost app's window titles
      read                    read visible text (Accessibility tree)
      capture [--full]        screenshot + on-device OCR (front window, or --full)
                              --no-ocr to just save the PNG and print its path
      status                  show whether control is on/off
    """
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(_main.__doc__)
        return 0

    cmd = argv[0]
    rest = argv[1:]

    if cmd == "status":
        print(status())
        return 0

    # Running this CLI is an explicit, present-user request, so enable control
    # for the invocation. (The env gate still governs programmatic/library use.)
    enable(True)
    # Read/capture are read-only and never mutate, so no confirmation hook needed.

    if cmd == "app":
        print(current_app())
    elif cmd == "windows":
        print(list_windows())
    elif cmd == "read":
        print(read_screen_text())
    elif cmd == "capture":
        scope = "full" if "--full" in rest else "window"
        ocr = "--no-ocr" not in rest
        print(capture_screen(scope=scope, ocr=ocr))
    else:
        print(f"unknown command: {cmd}\n")
        print(_main.__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
