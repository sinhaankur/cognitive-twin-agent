"""
desktop — the one entry point every cross-platform package launches.

The macOS app is a native Swift shell; on Linux and Windows the "Vera app" is
this: start her brain + voice server (``cognitive_twin.voice.server``) and open
her web UI in the browser. Pure-Python, standard-library HTTP — the same server
the Mac app talks to — so it runs identically on Linux, Windows, and macOS.

This is what the Flatpak / AppImage / MSIX / winget packages invoke:

    vera-app                 # console script (see pyproject [project.scripts])
    python -m cognitive_twin.desktop

It is deliberately thin: all the real work lives in the server. It only resolves
the port, honours a few env overrides, and hands off to ``serve``. Nothing here
reaches the network beyond binding localhost; the model runs on-device.
"""

from __future__ import annotations

import os
import sys


def _port() -> int:
    """The UI port — env override, else the server's default (7878)."""
    raw = os.environ.get("VERA_PORT") or os.environ.get("CTWIN_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    from .voice.server import DEFAULT_PORT
    return DEFAULT_PORT


def main(argv: list[str] | None = None) -> int:
    """Launch Vera's brain + web UI. Returns a process exit code.

    Flags (all optional; packages normally pass none):
      --port N      bind the UI to port N (else $VERA_PORT or 7878)
      --no-open     don't auto-open the browser (headless / server boxes)
      --host H      bind address (default localhost; 0.0.0.0 exposes on the
                    tailnet — only do this on a box you trust)
    """
    import argparse

    ap = argparse.ArgumentParser(
        prog="vera-app",
        description="Launch Vera — her brain + web UI, on-device.",
    )
    ap.add_argument("--port", type=int, default=_port())
    ap.add_argument("--no-open", action="store_true",
                    help="don't auto-open the browser")
    ap.add_argument("--host", default=None,
                    help="bind address (default localhost; 0.0.0.0 = tailnet)")
    args = ap.parse_args(argv)

    # host override flows through the same env the server already reads, so we
    # don't fork the server's binding logic.
    if args.host:
        os.environ["VERA_HOST"] = args.host

    try:
        from .voice.server import serve
    except Exception as e:  # pragma: no cover - import-time env problems
        print(f"[vera] couldn't load the brain server: {e}", file=sys.stderr)
        print("[vera] is the package installed with its dependencies "
              "(pip install -e .)?", file=sys.stderr)
        return 1

    try:
        serve(port=args.port, open_browser=not args.no_open)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
