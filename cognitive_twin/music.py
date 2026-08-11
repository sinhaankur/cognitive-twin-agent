"""
music — the music you actually listen to, so Vera knows your taste, not just that
sound is playing.

The Ear (EarEngine, SoundAnalysis) hears that *music is playing* in the room, on
purpose never *which song* — a privacy line held there. This module is the other
side, opt-in and explicit: when you turn it on, Vera reads macOS **Now Playing**
(Apple Music / Spotify, via AppleScript — no API key, nothing streamed) and keeps
a sealed local log of the tracks you play. From that she can tell you your top
artists, your most-played tracks, and how your listening shifts over time.

YouTube too: macOS 26 gates the system Now-Playing framework for third parties,
so for music the app-scripting can't see (YouTube / YouTube Music in a browser) we
read the frontmost browser tab title ("Artist - Track - YouTube") and parse it —
only YouTube tabs, only while that tab is frontmost, never other browsing.

It mirrors places.py exactly — one sealed log, the same opt-in + pause/snooze
gates, the same device-bound sealing:
  - OFF by default. You opt in (``enable()``).
  - PRIVATE / SNOOZE hard-stops all intake — nothing is read or stored while on.
  - Every play line is sealed at rest with Vera's device-bound key (the security
    kernel / ``vault.py`` — ChaCha20-Poly1305, key in the macOS Keychain bound to
    THIS Mac + THIS account). Copy the file off this machine and it reads as noise.
  - It lives in ``~/.cognitive-twin/music.jsonl``, owner-only. Never uploaded.
    Clear it any time (``clear()``).

The host (app) samples on a timer; ``sample()`` reads Now Playing once and logs a
play only when the track actually CHANGES, so a 3-minute song is one row, not sixty.

CLI:
    python3 -m cognitive_twin.music now        # what's playing right now (no log)
    python3 -m cognitive_twin.music sample     # log the current track if it changed
    python3 -m cognitive_twin.music taste       # top artists + tracks, all time
    python3 -m cognitive_twin.music status
    python3 -m cognitive_twin.music enable | pause | resume | clear

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# reuse places' opt-in + pause/snooze gates verbatim so the two behave identically
from . import places as _gate


# ── storage (sealed via the kernel) ───────────────────────────────────────────
def _log_path() -> Path:
    from . import security

    return security.path("music.jsonl")


# ── opt-in + private/snooze gates — a SEPARATE switch from places ──────────────
def _flag(name: str) -> Path:
    return _gate._home() / f"music.{name}"


def enable() -> None:
    _flag("enabled").write_text("1", encoding="utf-8")


def disable() -> None:
    _flag("enabled").unlink(missing_ok=True)


def is_enabled() -> bool:
    return _flag("enabled").is_file()


# music honours the SAME global private/snooze as everything else (places owns it)
def is_paused() -> bool:
    return _gate.is_paused()


def _intake_allowed() -> bool:
    return is_enabled() and not is_paused()


# ── the one record a play produces ─────────────────────────────────────────────
@dataclass
class Play:
    """A track you played, at a moment. Times are ISO-8601 local strings."""
    title: str
    artist: str = ""
    album: str = ""
    app: str = "Music"            # "Music" | "Spotify"
    at: str = ""                  # ISO-8601 when we first saw it playing
    meta: dict[str, Any] = field(default_factory=dict)

    def day(self) -> str:
        return self.at[:10]

    def key(self) -> str:
        return (self.title.strip().lower(), self.artist.strip().lower())


# ── read Now Playing (AppleScript; no key, nothing leaves the Mac) ─────────────
def _now_playing() -> Play | None:
    """The current track from Music or Spotify, if either is playing. Read-only —
    never starts, pauses, or changes playback. Returns None if nothing's playing."""
    if sys.platform != "darwin":
        return None
    # Music.app first, then Spotify — whichever is actually playing wins.
    probes = [
        ("Music",
         'tell application "Music"\n'
         '  if it is running and player state is playing then\n'
         '    set t to name of current track\n'
         '    set a to artist of current track\n'
         '    set al to album of current track\n'
         '    return t & "||" & a & "||" & al\n'
         '  end if\n'
         'end tell'),
        ("Spotify",
         'tell application "Spotify"\n'
         '  if it is running and player state is playing then\n'
         '    set t to name of current track\n'
         '    set a to artist of current track\n'
         '    set al to album of current track\n'
         '    return t & "||" & a & "||" & al\n'
         '  end if\n'
         'end tell'),
    ]
    for app, script in probes:
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            continue
        out = (r.stdout or "").strip()
        if r.returncode == 0 and out and "||" in out:
            title, artist, album = (out.split("||") + ["", ""])[:3]
            title = title.strip()
            if title:
                return Play(title=title, artist=artist.strip(), album=album.strip(),
                            app=app, at=_dt.datetime.now().isoformat(timespec="seconds"))
    # Nothing from the music apps → try YouTube-in-the-browser. macOS 26 gates the
    # system Now Playing framework for third parties, so we read what we CAN see:
    # the frontmost browser window's title, which for a playing YouTube tab is
    # "Track - Artist - YouTube" (or "(NN) Track - YouTube"). Best-effort + honest —
    # only captured while that tab is frontmost; parsed conservatively.
    return _now_playing_browser()


# Browser window/tab title → a Play, for YouTube (and YouTube Music) audio the
# music apps can't see. Read via System Events (no per-browser scripting perms).
_BROWSERS = ("Google Chrome", "Brave Browser", "Safari", "Microsoft Edge", "Arc", "Firefox")


def _now_playing_browser() -> Play | None:
    if sys.platform != "darwin":
        return None
    script = (
        'tell application "System Events"\n'
        '  set p to first application process whose frontmost is true\n'
        '  set appName to name of p\n'
        '  set winTitle to ""\n'
        '  try\n'
        '    set winTitle to name of front window of p\n'
        '  end try\n'
        '  return appName & "||" & winTitle\n'
        'end tell'
    )
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    app, _, title = (r.stdout or "").strip().partition("||")
    app, title = app.strip(), title.strip()
    if app not in _BROWSERS or not title:
        return None
    parsed = _parse_youtube_title(title)
    if not parsed:
        return None
    track, artist = parsed
    return Play(title=track, artist=artist, album="", app=app,
                at=_dt.datetime.now().isoformat(timespec="seconds"),
                meta={"via": "browser-title"})


def _parse_youtube_title(title: str) -> tuple[str, str] | None:
    """Pull (track, artist) out of a browser title. Returns None when the tab
    isn't a YouTube media page (so we never log random browsing as 'music')."""
    import re

    t = title.strip()
    # Only treat YouTube tabs as plays — other sites' titles aren't music.
    if not re.search(r"-\s*YouTube(\s+Music)?\s*$", t, re.I):
        return None
    # Drop the trailing " - YouTube" / " - YouTube Music"
    t = re.sub(r"\s*-\s*YouTube(\s+Music)?\s*$", "", t, flags=re.I).strip()
    # Drop a leading unread/notification count like "(3) " Chrome adds
    t = re.sub(r"^\(\d+\)\s*", "", t).strip()
    if not t:
        return None
    # "Artist - Track" is the common music convention on YouTube; split on the
    # FIRST " - ". If there's no dash, we keep the whole thing as the track.
    if " - " in t:
        left, _, right = t.partition(" - ")
        return (right.strip(), left.strip())   # (track, artist)
    return (t, "")


# ── append (sealed) + change-detection ─────────────────────────────────────────
def _append(play: Play) -> None:
    from . import security

    security.append_line(_log_path(), asdict(play))


def _last() -> Play | None:
    plays = read_all()
    return plays[-1] if plays else None


def sample() -> Play | None:
    """Read Now Playing once and log it — but ONLY if the track changed since the
    last row (so one song = one play, not one per timer tick). Returns the logged
    Play, or None if nothing new/allowed."""
    if not _intake_allowed():
        return None
    cur = _now_playing()
    if cur is None:
        return None
    last = _last()
    if last is not None and last.key() == cur.key():
        return None  # same track still playing — don't double-log
    _append(cur)
    return cur


def now() -> Play | None:
    """What's playing right now, without logging anything. Read-only."""
    return _now_playing()


# ── read (unsealed on this device only) ────────────────────────────────────────
def read_all() -> list[Play]:
    from . import security

    out: list[Play] = []
    for data in security.read_lines(_log_path()):
        try:
            out.append(Play(**data))
        except Exception:
            continue
    return out


def clear() -> None:
    _log_path().unlink(missing_ok=True)


# ── taste analysis ─────────────────────────────────────────────────────────────
def top_artists(limit: int = 10, *, since_days: int | None = None) -> list[tuple[str, int]]:
    from collections import Counter

    plays = _scoped(since_days)
    c: Counter[str] = Counter(p.artist.strip() for p in plays if p.artist.strip())
    return c.most_common(limit)


def top_tracks(limit: int = 10, *, since_days: int | None = None) -> list[tuple[str, int]]:
    from collections import Counter

    plays = _scoped(since_days)
    c: Counter[str] = Counter(
        f"{p.title.strip()} — {p.artist.strip()}" if p.artist.strip() else p.title.strip()
        for p in plays if p.title.strip()
    )
    return c.most_common(limit)


def _scoped(since_days: int | None) -> list[Play]:
    plays = read_all()
    if since_days is None:
        return plays
    cutoff = _dt.date.today() - _dt.timedelta(days=max(1, since_days))
    out = []
    for p in plays:
        try:
            if _dt.date.fromisoformat(p.day()) >= cutoff:
                out.append(p)
        except ValueError:
            continue
    return out


def summarize_taste(*, since_days: int | None = None, top: int = 8) -> str:
    """Human read-out of what you listen to — the answer to 'what music do I play'."""
    if not is_enabled():
        return ("I'm not tracking your music yet — turn it on with "
                "`python3 -m cognitive_twin.music enable`. Then I read macOS Now "
                "Playing (Apple Music / Spotify), on-device and sealed.")
    plays = _scoped(since_days)
    if not plays:
        window = f"the last {since_days} days" if since_days else "your history"
        return f"No plays logged across {window} yet — play something and I'll start learning."
    scope = f"last {since_days} days" if since_days else "all time"
    artists = top_artists(top, since_days=since_days)
    tracks = top_tracks(top, since_days=since_days)
    lines = [f"What you listen to — {scope}: {len(plays)} plays."]
    if artists:
        lines.append("")
        lines.append("Top artists:")
        for i, (a, n) in enumerate(artists, 1):
            lines.append(f"  {i}. {a} — {n} play(s)")
    if tracks:
        lines.append("")
        lines.append("Most played:")
        for i, (t, n) in enumerate(tracks, 1):
            lines.append(f"  {i}. {t} — {n}×")
    return "\n".join(lines)


def status() -> str:
    n = len(read_all()) if _log_path().is_file() else 0
    state = "on" if is_enabled() else "off"
    if is_paused():
        state += " (paused)"
    return (f"Music: {state}. {n} play(s) logged, sealed to this Mac. "
            f"Log: {_log_path()}")


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "enable":
        enable(); print("✓ Music tracking on (opt-in). Reads Now Playing, sealed here."); return 0
    if cmd == "disable":
        disable(); print("✓ Music tracking off."); return 0
    if cmd == "pause":
        _gate.pause(); print("⏸ Paused — nothing is read or stored until resume."); return 0
    if cmd == "resume":
        _gate.resume(); print("▶ Resumed."); return 0
    if cmd == "clear":
        clear(); print("✓ Cleared the local music log."); return 0
    if cmd == "status":
        print(status()); return 0
    if cmd == "now":
        p = now()
        print(f"Now playing: {p.title} — {p.artist} ({p.app})" if p else "Nothing playing right now.")
        return 0
    if cmd == "sample":
        p = sample()
        print(f"Logged: {p.title} — {p.artist}" if p
              else "Nothing new to log (off, paused, same track, or silent).")
        return 0
    if cmd in ("taste", "music", "top"):
        days = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else None
        print(summarize_taste(since_days=days)); return 0
    print("usage: python3 -m cognitive_twin.music "
          "[now|sample|taste [days]|status|enable|pause|resume|clear]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
