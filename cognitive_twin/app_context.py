"""
App-aware screen reading — read & understand only.

Vera notices which app you're actually in and reads it the *right* way, because
no single method works everywhere:

  - Terminal / iTerm, TextEdit, Notes, Mail — expose their text cleanly through
    the macOS Accessibility tree, so we read that directly (fast, exact).
  - VS Code, Chrome/Brave, Figma, PDFs — draw their content as pixels, so the
    Accessibility tree comes back empty; for these we screenshot + on-device
    Vision OCR (see control.capture_screen).
  - Word / Pages — try Accessibility first (often works for the body text),
    fall back to OCR when it doesn't.
  - Anything unknown — try Accessibility, then OCR if it's empty.

This is strictly read-only: it identifies the app and returns what's on screen as
context the twin can reason over. It never types, clicks, or edits anything, and
it stays behind the same opt-in gate (CTWIN_CONTROL) as the rest of control.py.

Everything is local: Accessibility and screencapture are OS calls, OCR runs
on-device via Apple's Vision framework. Nothing is uploaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import control

# How to read a given app. "ax" = Accessibility text; "ocr" = screenshot+OCR;
# "ax_then_ocr" = Accessibility first, OCR if it yields nothing.
_AX = "ax"
_OCR = "ocr"
_AX_THEN_OCR = "ax_then_ocr"

# Frontmost-app name (as macOS reports it) → strategy. Names are matched
# case-insensitively and by substring, so "Google Chrome", "Microsoft Word",
# and "Code - Insiders" all resolve without an exact entry.
_STRATEGY: list[tuple[str, str]] = [
    # text-native apps: the accessibility tree is exact and instant
    ("terminal", _AX), ("iterm", _AX), ("warp", _AX), ("alacritty", _OCR),
    ("textedit", _AX), ("notes", _AX), ("mail", _AX), ("messages", _AX),
    ("script editor", _AX), ("console", _AX),
    # pixel-drawn apps: OCR is the only thing that sees the content
    ("code", _OCR), ("cursor", _OCR),         # VS Code / Cursor
    ("chrome", _OCR), ("brave", _OCR), ("arc", _OCR), ("firefox", _OCR),
    ("safari", _AX_THEN_OCR),                 # Safari exposes some text via AX
    ("figma", _OCR), ("preview", _OCR), ("acrobat", _OCR),
    ("photoshop", _OCR), ("slack", _OCR), ("discord", _OCR),
    # office: body text is often in the AX tree; OCR is the safety net
    ("word", _AX_THEN_OCR), ("pages", _AX_THEN_OCR),
    ("excel", _OCR), ("numbers", _OCR), ("powerpoint", _OCR), ("keynote", _OCR),
]

_DEFAULT_STRATEGY = _AX_THEN_OCR

# Alacritty/terminals that don't expose AX are marked OCR above; keep a note of
# which apps are terminals so the twin gets a helpful "you're at a shell" hint.
_TERMINALS = {"terminal", "iterm", "warp", "alacritty"}


def _app_name() -> str:
    """Bare frontmost-app name, or '' if control is off / it can't be read."""
    raw = control.current_app()  # "Frontmost app: X" or an "[...]" error
    if not raw or raw.startswith("["):
        return ""
    return raw.split(":", 1)[1].strip() if ":" in raw else raw.strip()


def _strategy_for(app: str) -> str:
    a = app.lower()
    for needle, strat in _STRATEGY:
        if needle in a:
            return strat
    return _DEFAULT_STRATEGY


@dataclass
class ScreenContext:
    app: str
    strategy: str          # which read method was used
    text: str              # what was read (may be an "[...]" note)
    is_terminal: bool = False

    def as_prompt(self) -> str:
        """A twin-ready block describing what the user is looking at."""
        if not self.app:
            return ""
        where = f"The user is currently in {self.app}."
        if self.is_terminal:
            where += " (a terminal/shell)"
        body = self.text.strip()
        if not body or body.startswith("["):
            return where + " (No readable on-screen text was available.)"
        return (where + " On-screen content (read-only, for context — reference it "
                "naturally, don't dump it back):\n" + body)


def _read_ax(max_chars: int) -> str:
    return control.read_screen_text(max_chars=max_chars)


_OCR_MARK = "--- on-screen text (Vision OCR) ---"


def _read_ocr(scope: str, max_chars: int) -> str:
    """OCR the screen and return just the recognized text. capture_screen()
    prepends a '[screenshot: ...]' header (and the OCR marker line); strip both
    so the caller sees only the content — otherwise the leading '[' would look
    like an error to the empties check."""
    out = control.capture_screen(scope=scope, ocr=True, max_chars=max_chars)
    if _OCR_MARK in out:
        return out.split(_OCR_MARK, 1)[1].strip()
    # no OCR body (save-only, permission error, or no text) — pass through so the
    # caller's empties check can react to the "[...]" / empty result.
    return out.strip()


def read_active(*, max_chars: int = 3000, scope: str = "window") -> ScreenContext:
    """Read whatever app is frontmost, using the best method for it.

    Read-only. Returns a ScreenContext with the app name, the strategy used, and
    the text (or an empty/"[...]" note when nothing was readable). Honors the
    control.py opt-in gate — if control is off, the text carries that message.
    """
    if (err := control._require_enabled()):
        return ScreenContext(app="", strategy="", text=err)

    app = _app_name()
    strat = _strategy_for(app)
    is_term = any(t in app.lower() for t in _TERMINALS)

    if strat == _AX:
        text = _read_ax(max_chars)
    elif strat == _OCR:
        text = _read_ocr(scope, max_chars)
    else:  # ax_then_ocr
        text = _read_ax(max_chars)
        empty = (not text.strip()) or text.startswith("[no readable text]") \
            or text.startswith("[error]")
        if empty:
            text = _read_ocr(scope, max_chars)
            strat = _AX_THEN_OCR + " (fell back to OCR)"

    return ScreenContext(app=app, strategy=strat, text=text, is_terminal=is_term)


# ---- CLI ----------------------------------------------------------------------
def _main(argv: list[str]) -> int:
    """python3 -m cognitive_twin.app_context [--full] [--raw]

    Print what Vera reads from the frontmost app, choosing AX vs OCR by app.
      --full   capture the whole display instead of just the front window (OCR apps)
      --raw    print only the read text, without the 'you're in X' framing
    """
    if argv and argv[0] in {"-h", "--help", "help"}:
        print(_main.__doc__)
        return 0
    control.enable(True)  # explicit present-user request via the CLI
    scope = "full" if "--full" in argv else "window"
    ctx = read_active(scope=scope)
    if "--raw" in argv:
        print(ctx.text)
    else:
        print(f"[app] {ctx.app or '(unknown)'}  [read via] {ctx.strategy or '(n/a)'}")
        print(ctx.as_prompt())
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
