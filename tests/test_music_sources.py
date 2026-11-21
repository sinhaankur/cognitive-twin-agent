"""
music — she knows what you ACTUALLY listen to: YouTube AND SoundCloud (the sites
you use), parsed from the browser tab, plus Apple Music / Spotify. And she can
reference your taste in conversation (context_for_prompt), only when it's on.
"""
from __future__ import annotations

import datetime as dt
import tempfile

from cognitive_twin import music


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_parses_soundcloud_titles():
    # plain, with the play glyph, and the "Stream …" page variant
    assert music._parse_browser_title(
        "Experience by Ludovico Einaudi | Listen online for free on SoundCloud"
    ) == ("Experience", "Ludovico Einaudi", "soundcloud")
    assert music._parse_browser_title(
        "▶ Nuvole Bianche by Ludovico Einaudi | Listen online for free on SoundCloud"
    ) == ("Nuvole Bianche", "Ludovico Einaudi", "soundcloud")
    assert music._parse_browser_title(
        "Stream Weightless by Marconi Union | Listen online for free on SoundCloud"
    ) == ("Weightless", "Marconi Union", "soundcloud")


def test_parses_youtube_titles():
    assert music._parse_browser_title(
        "Ludovico Einaudi - Nuvole Bianche - YouTube"
    ) == ("Nuvole Bianche", "Ludovico Einaudi", "youtube")
    # a leading "(3)" unread count is stripped
    assert music._parse_browser_title(
        "(3) lofi hip hop radio - beats to relax - YouTube"
    ) == ("beats to relax", "lofi hip hop radio", "youtube")


def test_non_music_tabs_are_ignored():
    assert music._parse_browser_title("Some Article - The Verge") is None
    assert music._parse_browser_title("Inbox (12) - Gmail") is None
    assert music._parse_browser_title("") is None


def test_back_compat_youtube_alias():
    # the old 2-tuple name still works for any existing callers
    assert music._parse_youtube_title("A - B - YouTube") == ("B", "A")


def test_context_is_empty_when_off(monkeypatch):
    _fresh(monkeypatch)
    assert music.is_enabled() is False
    assert music.context_for_prompt() == ""     # off → says nothing, never guesses


def test_context_surfaces_taste_when_on(monkeypatch):
    _fresh(monkeypatch)
    music.enable()
    for t, a in [("Experience", "Ludovico Einaudi"),
                 ("Nuvole Bianche", "Ludovico Einaudi"),
                 ("Weightless", "Marconi Union")]:
        music._append(music.Play(title=t, artist=a, app="Chrome",
                                 at=dt.datetime.now().isoformat(timespec="seconds"),
                                 meta={"via": "soundcloud"}))
    ctx = music.context_for_prompt()
    assert "Ludovico Einaudi" in ctx            # she knows the top artist
    assert "music" in ctx.lower()
    # it steers her to use it naturally, not recite stats
    assert "like a friend" in ctx
