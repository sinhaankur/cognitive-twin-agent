"""
Built-in MVP skills — safe, local, useful. Importing this module registers them
on the default registry. All file access is sandboxed to a working directory so
the agent can't wander the filesystem.
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from .base import default_registry as R

# Sandbox root for file skills — defaults to ~/.cognitive-twin/workspace, override
# with CTWIN_WORKSPACE. Created on first use.
def _workspace() -> Path:
    root = Path(os.environ.get("CTWIN_WORKSPACE", Path.home() / ".cognitive-twin" / "workspace"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()

def _safe_path(rel: str) -> Path:
    """Resolve rel inside the workspace; reject escapes (../, absolute)."""
    root = _workspace()
    p = (root / rel).resolve()
    if root not in p.parents and p != root:
        raise ValueError(f"path '{rel}' is outside the workspace sandbox")
    return p


@R.add("now", "Get the current date and time (local).")
def now() -> str:
    n = _dt.datetime.now()
    return n.strftime("%A, %B %d, %Y · %H:%M")


@R.add(
    "list_dir",
    "List files in a folder inside the workspace.",
    {"type": "object", "properties": {"path": {"type": "string", "description": "folder relative to the workspace; '' for root"}}},
)
def list_dir(path: str = "") -> str:
    p = _safe_path(path or ".")
    if not p.exists():
        return f"[empty] '{path or '.'}' does not exist in the workspace"
    items = sorted(os.listdir(p))
    return "\n".join(items) if items else "[empty]"


@R.add(
    "read_file",
    "Read a UTF-8 text file from the workspace (first ~8 KB).",
    {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)
def read_file(path: str) -> str:
    p = _safe_path(path)
    if not p.is_file():
        return f"[not found] '{path}'"
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[:8000] + ("\n…[truncated]" if len(text) > 8000 else "")


@R.add(
    "daily_digest",
    "Build a digest of today from LOCAL signals: today's date plus the user's "
    "tasks/notes file in the workspace (tasks.md by default) and an optional .ics "
    "calendar. Use this to summarize the user's day.",
    {"type": "object", "properties": {
        "tasks_file": {"type": "string", "description": "tasks/notes filename in workspace (default tasks.md)"},
        "calendar_file": {"type": "string", "description": "optional .ics filename in workspace"},
    }},
)
def daily_digest(tasks_file: str = "tasks.md", calendar_file: str = "") -> str:
    today = _dt.date.today()
    out: list[str] = [f"Date: {today.strftime('%A, %B %d, %Y')}"]

    # tasks/notes
    try:
        tp = _safe_path(tasks_file)
        if tp.is_file():
            lines = [ln.strip() for ln in tp.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            out.append(f"\nTasks/notes ({tasks_file}) — {len(lines)} item(s):")
            out.extend(f"  • {ln.lstrip('-* ').strip()}" for ln in lines[:20])
        else:
            out.append(f"\nNo tasks file at '{tasks_file}' in the workspace — add one to enrich the digest.")
    except ValueError as e:
        out.append(f"\n[skip tasks] {e}")

    # very light .ics parse — today's VEVENT SUMMARY lines (no external deps)
    if calendar_file:
        try:
            cp = _safe_path(calendar_file)
            if cp.is_file():
                events = _today_events(cp.read_text(encoding="utf-8", errors="replace"), today)
                out.append(f"\nToday's calendar ({calendar_file}) — {len(events)} event(s):")
                out.extend(f"  • {e}" for e in events[:20])
            else:
                out.append(f"\nNo calendar at '{calendar_file}'.")
        except ValueError as e:
            out.append(f"\n[skip calendar] {e}")

    return "\n".join(out)


@R.add(
    "thoughts_of_the_day",
    "Generate the user's 'thoughts of the day': a short, personal reflection "
    "drawing on LOCAL context — today's date, the user's tasks, and their private "
    "on-device history of recurring interests. Use this when the user asks for "
    "thoughts of the day, a daily reflection, or what's on their mind.",
    {"type": "object", "properties": {
        "tasks_file": {"type": "string", "description": "tasks/notes filename (default tasks.md)"},
    }},
)
def thoughts_of_the_day(tasks_file: str = "tasks.md") -> str:
    """Return raw, local material for a daily reflection. The model shapes this
    into thoughts written in the user's own voice (twin-mimicry)."""
    from .. import memory  # local import to avoid a cycle at module load

    today = _dt.date.today()
    out: list[str] = [f"Today is {today.strftime('%A, %B %d, %Y')}."]

    # today's tasks
    try:
        tp = _safe_path(tasks_file)
        if tp.is_file():
            lines = [ln.strip().lstrip("-* ").strip()
                     for ln in tp.read_text(encoding="utf-8", errors="replace").splitlines()
                     if ln.strip()]
            if lines:
                out.append("On the plate today: " + "; ".join(lines[:8]) + ".")
    except ValueError:
        pass

    # private, on-device patterns
    p = memory.patterns()
    if p.get("topics"):
        out.append("Lately the user keeps returning to: " + ", ".join(p["topics"]) + ".")
    recent = memory.recent_prompts(3)
    if recent:
        out.append("Recently they asked about: " + " / ".join(recent) + ".")

    style = ""
    try:
        from .. import mood
        style = mood.reflection_style()
    except Exception:
        pass
    out.append(
        "\nGive ONE single-sentence thought of the day for this person — short, "
        "warm, and specific to their day. One line only, no list, no preamble." + style
    )
    return "\n".join(out)


# ---- web (opt-in internet access) --------------------------------------------
# Local-first by default, but the twin can reach the internet when you allow it.
# Off unless CTWIN_WEB=1 (so the default install never makes network calls).

def _web_enabled() -> bool:
    import os as _os
    return _os.environ.get("CTWIN_WEB", "").strip() in {"1", "true", "yes", "on"}


@R.add("greeting", "Produce a time-aware greeting (good morning/afternoon/evening) "
       "with today's date and — if internet is on — the current local weather. Use "
       "to open a session or when the user says hi / asks for a greeting.")
def greeting() -> str:
    now = _dt.datetime.now()
    h = now.hour
    part = ("morning" if h < 12 else "afternoon" if h < 18 else "evening")
    out = [f"Good {part}! It's {now.strftime('%A, %B %d')}, {now.strftime('%H:%M')}."]

    if _web_enabled():
        w = _weather_now()
        if w:
            out.append(w)
    else:
        out.append("(Turn on internet with CTWIN_WEB=1 for live weather.)")
    return " ".join(out)


def _weather_now() -> str:
    """Current weather via open-meteo (no API key). IP-geolocates first."""
    import json as _json
    import urllib.request as _req
    import urllib.error as _err
    ua = {"User-Agent": "CognitiveTwin/0.1"}
    try:
        # rough location from IP
        with _req.urlopen(_req.Request("https://ipapi.co/json/", headers=ua), timeout=8) as r:
            loc = _json.loads(r.read().decode("utf-8", "replace"))
        lat, lon = loc.get("latitude"), loc.get("longitude")
        city = loc.get("city", "")
        if lat is None or lon is None:
            return ""
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               "&current=temperature_2m,weather_code&temperature_unit=celsius")
        with _req.urlopen(_req.Request(url, headers=ua), timeout=8) as r:
            wx = _json.loads(r.read().decode("utf-8", "replace"))
        cur = wx.get("current", {})
        temp = cur.get("temperature_2m")
        desc = _WMO.get(cur.get("weather_code"), "")
        where = f" in {city}" if city else ""
        if temp is not None:
            return f"It's {round(temp)}°C{where}{(' — ' + desc) if desc else ''}."
        return ""
    except (_err.URLError, _err.HTTPError, ValueError, KeyError):
        return ""


# WMO weather codes → short text
_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "heavy showers",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


@R.add("web_search", "Search the internet and return the top results (title, URL, "
       "snippet). Use this to answer questions about current events, facts, or "
       "anything you don't already know. Requires internet access to be enabled.",
       {"type": "object", "properties": {
           "query": {"type": "string", "description": "what to search for"}},
        "required": ["query"]})
def web_search(query: str) -> str:
    if not _web_enabled():
        return ("[web disabled] Internet access is off (local-first default). "
                "Enable it with CTWIN_WEB=1.")
    import html as _htmlmod
    import re as _re
    import urllib.parse as _parse
    import urllib.request as _req
    import urllib.error as _err
    q = (query or "").strip()
    if not q:
        return "[refused] empty query."
    # DuckDuckGo Lite — stable markup, expects a POST. No API key.
    data = _parse.urlencode({"q": q}).encode()
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    try:
        r = _req.Request("https://lite.duckduckgo.com/lite/", data=data,
                         headers={"User-Agent": ua})
        with _req.urlopen(r, timeout=15) as resp:
            page = resp.read(400_000).decode("utf-8", errors="replace")
    except (_err.URLError, _err.HTTPError) as e:
        return f"[error] search failed: {e}"

    def _clean(s: str) -> str:
        s = _re.sub(r"(?s)<[^>]+>", "", s)
        return _htmlmod.unescape(_re.sub(r"\s+", " ", s)).strip()

    # Lite markup: <a ... href="URL" class='result-link'>TITLE</a> and
    # <td class='result-snippet'>SNIPPET</td>
    links = _re.findall(
        r'<a[^>]*href="(http[^"]+)"[^>]*class=[\'"]result-link[\'"][^>]*>(.*?)</a>',
        page, _re.S)
    snippets = _re.findall(
        r'<td[^>]*class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', page, _re.S)

    results: list[str] = []
    for i, (href, title) in enumerate(links[:5]):
        snip = _clean(snippets[i]) if i < len(snippets) else ""
        results.append(f"{i+1}. {_clean(title)}\n   {href}\n   {snip}")

    if not results:
        return f"[no results] for '{q}'."
    return (f"Top results for “{q}”:\n\n" + "\n\n".join(results)
            + "\n\nTo read one in full, use fetch_url with its link.")


@R.add("fetch_url", "Fetch a web page and return its readable text. Use when the "
       "user asks about something online or gives a URL. Requires internet access "
       "to be enabled.",
       {"type": "object", "properties": {
           "url": {"type": "string", "description": "an http(s) URL"}},
        "required": ["url"]})
def fetch_url(url: str) -> str:
    if not _web_enabled():
        return ("[web disabled] Internet access is off (local-first default). "
                "Enable it with CTWIN_WEB=1.")
    import re as _re
    import urllib.request as _req
    import urllib.error as _err
    url = (url or "").strip()
    if not _re.match(r"^https?://", url, _re.IGNORECASE):
        return "[refused] Only http(s) URLs are allowed."
    try:
        r = _req.Request(url, headers={"User-Agent": "CognitiveTwin/0.1 (local)"})
        with _req.urlopen(r, timeout=15) as resp:
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read(600_000)  # cap ~600KB
        text = raw.decode("utf-8", errors="replace")
        if "html" in ctype.lower() or text.lstrip().startswith("<"):
            text = _re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
            text = _re.sub(r"(?s)<[^>]+>", " ", text)
            text = _re.sub(r"\s+", " ", text)
        text = text.strip()
        return text[:4000] + ("…[truncated]" if len(text) > 4000 else "")
    except (_err.URLError, _err.HTTPError) as e:
        return f"[error] couldn't fetch {url}: {e}"
    except Exception as e:
        return f"[error] {e}"


# ---- screen control (opt-in, permissioned, safe) -----------------------------
# These delegate to control.py, which enforces the opt-in gate + per-action
# confirmation. They no-op with a clear message when control is off.

@R.add("see_screen", "See what's on screen right now: the frontmost app and its "
       "open windows. Read-only. Use when the user asks what they're looking at.")
def see_screen() -> str:
    from .. import control
    return control.current_app() + "\n" + control.list_windows()


@R.add("read_screen", "Read the visible text of the frontmost window (read-only). "
       "Use to answer questions about on-screen content.")
def read_screen() -> str:
    from .. import control
    return control.read_screen_text()


@R.add("capture_screen", "Screenshot the screen and read its text with on-device "
       "OCR (read-only). Use when read_screen finds no text — e.g. a browser "
       "canvas, an image, a video frame, or an app like VS Code that draws its "
       "text as pixels. scope 'window' (front window) or 'full' (whole display).",
       {"type": "object", "properties": {
           "scope": {"type": "string", "enum": ["window", "full"],
                     "description": "front window (default) or the full screen"}},
        "required": []})
def capture_screen(scope: str = "window") -> str:
    from .. import control
    return control.capture_screen(scope=scope)


@R.add("read_active_app", "Read whatever app the user is currently in — Vera picks "
       "the best method per app (Accessibility text for Terminal/Notes/Mail, "
       "screenshot+OCR for VS Code/browsers/PDFs). Read-only. Use to understand "
       "what the user is working on right now, e.g. their code, terminal, or doc.")
def read_active_app() -> str:
    from .. import app_context
    return app_context.read_active().as_prompt()


@R.add("open_app", "Open a macOS app by name (asks the user to confirm first).",
       {"type": "object", "properties": {"name": {"type": "string", "description": "app name, e.g. Safari"}},
        "required": ["name"]})
def open_app(name: str) -> str:
    from .. import control
    return control.open_app(name)


@R.add("open_url", "Open an http(s) URL in the browser (asks the user to confirm first).",
       {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]})
def open_url(url: str) -> str:
    from .. import control
    return control.open_url(url)


@R.add("run_shortcut", "Run a macOS Shortcut by name (asks the user to confirm first).",
       {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})
def run_shortcut(name: str) -> str:
    from .. import control
    return control.run_shortcut(name)


# ---- camera + microphone (opt-in, permissioned, off by default) ---------------
# Delegate to media.py, which enforces the per-device gate + per-capture
# confirmation. They no-op with a clear message when the device is off, and the
# captured file stays local — nothing is uploaded.

@R.add("take_photo", "Take a single photo with the webcam (off by default; asks "
       "the user to confirm, and only works if the camera is enabled).")
def take_photo() -> str:
    from .. import media
    return media.capture_photo()


@R.add("record_audio", "Record a short clip from the microphone (off by default; "
       "asks the user to confirm, and only works if the mic is enabled).",
       {"type": "object", "properties": {"seconds": {"type": "number"}}})
def record_audio(seconds: float = 4.0) -> str:
    from .. import media
    return media.record_audio(seconds)


def _today_events(ics: str, today: _dt.date) -> list[str]:
    """Minimal .ics: collect SUMMARY of VEVENTs whose DTSTART is today."""
    events: list[str] = []
    cur: dict[str, str] = {}
    in_event = False
    stamp = today.strftime("%Y%m%d")
    for raw in ics.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            in_event, cur = True, {}
        elif line == "END:VEVENT":
            if in_event and cur.get("start", "").startswith(stamp):
                events.append(cur.get("summary", "(untitled)"))
            in_event = False
        elif in_event:
            if line.startswith("DTSTART"):
                cur["start"] = line.split(":", 1)[-1]
            elif line.startswith("SUMMARY"):
                cur["summary"] = line.split(":", 1)[-1]
    return events
