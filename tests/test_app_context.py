"""
App-context tests — the app→strategy mapping and the prompt framing are pure
functions of the app name + read text, so we test them without touching the
screen (no AppleScript, no screencapture). read_active() itself needs a live
macOS session, so it isn't exercised here.

Run: python -m pytest tests/ -q   (or: python tests/test_app_context.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin import app_context as ac  # noqa: E402


def test_terminal_uses_accessibility():
    assert ac._strategy_for("Terminal") == ac._AX
    assert ac._strategy_for("iTerm2") == ac._AX


def test_vscode_and_browsers_use_ocr():
    assert ac._strategy_for("Code") == ac._OCR
    assert ac._strategy_for("Code - Insiders") == ac._OCR   # substring match
    assert ac._strategy_for("Google Chrome") == ac._OCR
    assert ac._strategy_for("Brave Browser") == ac._OCR


def test_word_uses_ax_then_ocr():
    assert ac._strategy_for("Microsoft Word") == ac._AX_THEN_OCR
    assert ac._strategy_for("Pages") == ac._AX_THEN_OCR


def test_unknown_app_defaults_to_ax_then_ocr():
    assert ac._strategy_for("SomeRandomApp 3000") == ac._DEFAULT_STRATEGY
    assert ac._DEFAULT_STRATEGY == ac._AX_THEN_OCR


def test_prompt_framing_for_terminal():
    ctx = ac.ScreenContext(app="Terminal", strategy=ac._AX,
                           text="$ ls\nfile.py", is_terminal=True)
    p = ctx.as_prompt()
    assert "Terminal" in p and "terminal/shell" in p
    assert "file.py" in p


def test_prompt_framing_when_no_text():
    ctx = ac.ScreenContext(app="Code", strategy=ac._OCR, text="")
    p = ctx.as_prompt()
    assert "Code" in p
    assert "No readable on-screen text" in p


def test_prompt_empty_when_no_app():
    ctx = ac.ScreenContext(app="", strategy="", text="[control disabled] ...")
    assert ctx.as_prompt() == ""


def test_bracketed_text_treated_as_no_content():
    # an "[error]" / "[no readable text]" note must not be surfaced as content
    ctx = ac.ScreenContext(app="Word", strategy="ax", text="[no readable text] ...")
    p = ctx.as_prompt()
    assert "No readable on-screen text" in p


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
