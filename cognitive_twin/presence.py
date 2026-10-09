"""
presence.py — her sense of you, right now (opt-in camera, on-device).

Two eyes feed this, both opt-in behind "See me", both fully on-device:
  - the Mac app: Apple Vision face landmarks (FaceEngine.swift) — real facial
    geometry: smile, knitted brow, blink rate, attention, nod/shake, lean
  - the browser page: the owner's optical-flow engine (Shi-Tomasi + pyramidal
    Lucas-Kanade, ported from sinhaankur.com/lab/optical-flow) — motion only

No frame ever leaves the sender: only a handful of derived signals arrive
here, and this module holds just the LATEST reading, in process memory.

A THIRD sense, added here, needs no camera: the DEVICE ecosystem. The eyes see
the person; this reads the *situation* around the moment — is a call or meeting
running, is a video playing, is music on, or are you heads-down working — from
what's on screen (frontmost app) and whether the microphone is live. Ankur's
principle: *"if the ecosystem difference is not understood, the chat won't make
sense."* A companion that answers mid-meeting isn't present, it's intrusive, so
this lets her hold back. It is reactive only (it changes HOW she replies when you
DO talk to her, never makes her speak first), opt-in, and — like everything in
presence — stores NOTHING.

Ephemeral by design: presence is the present tense. Nothing is written to disk,
nothing enters memory.jsonl, and a reading older than a few seconds is treated
as gone. Honesty rule: these are *measured* facts — "smiling" is a mouth shape,
"brow knitted" is a distance — never invented emotions ("sad", "stressed");
the agent may respond to what the camera actually measured, not to a guess
dressed as a fact. The device read is the same: "the mic is live" and "Zoom is in
front" are observations, offered with a confidence, never an assumption.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import struct
import sys
import time
from typing import Any

_STALE_S = 15.0
_last: dict[str, Any] | None = None


def _unit(v: Any) -> float | None:
    """A 0..1 signal, or None when the sender didn't measure it."""
    if v is None:
        return None
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def _signed(v: Any) -> float | None:
    """A -1..1 signal (a trend slope: negative falling, positive rising), or None."""
    if v is None:
        return None
    try:
        return max(-1.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def update(sig: dict[str, Any]) -> None:
    """Store the latest derived reading from the (opt-in) camera sender."""
    global _last
    _last = {
        "present": bool(sig.get("present")),
        "energy": max(0.0, min(1.0, float(sig.get("energy") or 0.0))),
        "gesture": sig.get("gesture") if sig.get("gesture") in ("nod", "shake") else None,
        "lean": sig.get("lean") if sig.get("lean") in ("in", "out") else None,
        # facial geometry — only the app's Vision eye sends these; the browser
        # eye measures motion alone, so they stay None there (honest absence)
        "smile": _unit(sig.get("smile")),
        "brow": _unit(sig.get("brow")),
        "frown": _unit(sig.get("frown")),
        "blink_rate": (float(sig["blink_rate"]) if isinstance(sig.get("blink_rate"), (int, float)) else None),
        "attending": (bool(sig["attending"]) if sig.get("attending") is not None else None),
        # READING THE ROOM — how many people are in view, how many are looking
        # toward her, a plain social-context line, and whether a voice right now
        # is likely meant for Vera vs. the people around you. Measured (face
        # count + yaw), never guessed. Lets her know when NOT to jump in.
        "people": (int(sig["people"]) if isinstance(sig.get("people"), (int, float)) else None),
        "people_attending": (int(sig["people_attending"]) if isinstance(sig.get("people_attending"), (int, float)) else None),
        "room_context": (sig.get("room_context") if isinstance(sig.get("room_context"), str) and sig.get("room_context") else None),
        "addressing_her": (bool(sig["addressing_her"]) if sig.get("addressing_her") is not None else None),
        # FEELING OVER TIME — the arc of the face, not the still frame. A plain
        # phrase ("brightening", "winding down") plus signed trend magnitudes, sent
        # only while something is actually moving. Lets her respond to the SHIFT.
        "trend": (sig.get("trend") if isinstance(sig.get("trend"), str) and sig.get("trend") else None),
        "trend_mood": _signed(sig.get("trend_mood")),
        "trend_tension": _signed(sig.get("trend_tension")),
        "trend_energy": _signed(sig.get("trend_energy")),
        "source": sig.get("source") if sig.get("source") in ("face", "flow") else "flow",
        "ts": time.time(),
    }


def stop() -> None:
    """The user turned the camera off — forget immediately."""
    global _last
    _last = None


# ---- the ear: ambient sound (opt-in, on-device, never recorded) ---------------
_AMBIENT_STALE_S = 20.0
_ambient: dict[str, Any] | None = None


def update_ambient(sig: dict[str, Any]) -> None:
    """Latest ambient reading from the app's opt-in ear: sound TYPES with
    confidence (Apple's on-device classifier) + room loudness. No audio."""
    global _ambient
    sounds: list[dict[str, Any]] = []
    for s in (sig.get("sounds") or [])[:3]:
        label = str((s or {}).get("label") or "").strip()
        conf = _unit((s or {}).get("conf")) or 0.0
        if label and conf >= 0.45:
            sounds.append({"label": label, "conf": conf})
    _ambient = {
        "sounds": sounds,
        "loud": _unit(sig.get("loud")) or 0.0,
        "ts": time.time(),
    }


def stop_ambient() -> None:
    """The user turned the ear off — forget the room immediately."""
    global _ambient
    _ambient = None


def ambient_current() -> dict[str, Any] | None:
    if _ambient is None or (time.time() - _ambient["ts"]) > _AMBIENT_STALE_S:
        return None
    return dict(_ambient)


def _loud_word(l: float) -> str:
    if l < 0.12:
        return "quiet"
    if l < 0.4:
        return "lively"
    return "loud"


def current() -> dict[str, Any] | None:
    """The latest reading, or None when off/stale (presence never lingers)."""
    if _last is None or (time.time() - _last["ts"]) > _STALE_S:
        return None
    return dict(_last)


def _energy_word(e: float) -> str:
    if e < 0.08:
        return "very still"
    if e < 0.28:
        return "calm"
    if e < 0.6:
        return "animated"
    return "very animated"


# ─────────────────────────────────────────────────────────────────────────────
# THE DEVICE SENSE — the ecosystem around the moment (no camera, nothing stored)
# ─────────────────────────────────────────────────────────────────────────────
# A SEPARATE opt-in switch from "See me" (the camera). Off by default. Honours the
# same global private/snooze gate as every other sense (places owns it).
def _device_flag():
    from . import places as _gate
    return _gate._home() / "presence.device.enabled"


def enable_device() -> None:
    _device_flag().write_text("1", encoding="utf-8")


def disable_device() -> None:
    _device_flag().unlink(missing_ok=True)


def device_enabled() -> bool:
    return _device_flag().is_file()


def _device_allowed() -> bool:
    from . import places as _gate
    return device_enabled() and not _gate.is_paused()


# apps/sites that mean a live conversation is happening — never talk over it.
_MEETING_APPS = {
    "zoom.us", "zoom", "Microsoft Teams", "Teams", "Webex", "Cisco Webex Meetings",
    "Google Meet", "Skype", "GoToMeeting", "BlueJeans", "Around", "Whereby",
}
_MEETING_TABS = ("meet.google.com", "google meet", "zoom meeting", "teams meeting",
                 "webex", "whereby", "- meet")
_VIDEO_APPS = {"QuickTime Player", "VLC", "Netflix", "TV", "IINA"}
_VIDEO_TABS = ("youtube", "netflix", "- twitch", "vimeo", "disney+", "prime video",
               "hulu", " max")
_COMMS_APPS = {"Slack", "Discord", "FaceTime"}
_BROWSERS = {"Google Chrome", "Brave Browser", "Safari", "Microsoft Edge", "Arc", "Firefox"}


def _fourcc(s: str) -> int:
    return struct.unpack(">I", s.encode())[0]


def mic_active() -> bool | None:
    """True if *some* process is capturing the default input device right now — the
    honest signal for 'you're probably on a call'. Device-global via CoreAudio's
    kAudioDevicePropertyDeviceIsRunningSomewhere; no sudo, no PyObjC. None when
    it can't be read (non-macOS / no CoreAudio / error)."""
    if sys.platform != "darwin":
        return None
    libpath = ctypes.util.find_library("CoreAudio")
    if not libpath:
        return None
    try:
        ca = ctypes.CDLL(libpath)
    except OSError:
        return None

    class AOPA(ctypes.Structure):
        _fields_ = [("mSelector", ctypes.c_uint32),
                    ("mScope", ctypes.c_uint32),
                    ("mElement", ctypes.c_uint32)]

    kSystemObject, kScopeGlobal, kElementMain = 1, _fourcc("glob"), 0
    try:
        dev = ctypes.c_uint32(0); size = ctypes.c_uint32(4)
        a1 = AOPA(_fourcc("dIn "), kScopeGlobal, kElementMain)
        if ca.AudioObjectGetPropertyData(kSystemObject, ctypes.byref(a1), 0, None,
                                         ctypes.byref(size), ctypes.byref(dev)) != 0 or dev.value == 0:
            return None
        running = ctypes.c_uint32(0); size = ctypes.c_uint32(4)
        a2 = AOPA(_fourcc("gone"), kScopeGlobal, kElementMain)
        if ca.AudioObjectGetPropertyData(dev.value, ctypes.byref(a2), 0, None,
                                         ctypes.byref(size), ctypes.byref(running)) != 0:
            return None
        return bool(running.value)
    except Exception:
        return None


def _frontmost() -> tuple[str, str]:
    """(app, window title) of the frontmost app — reused from activity.py so there's
    one probe, not two. ('', '') on failure / non-macOS."""
    try:
        from . import activity
        return activity._frontmost()
    except Exception:
        return ("", "")


def _music_playing() -> bool:
    try:
        from . import music
        return music.now() is not None
    except Exception:
        return False


def _tab_hits(title: str, needles) -> bool:
    low = title.lower()
    return any(n in low for n in needles)


def device_now() -> dict[str, Any]:
    """Read the device ecosystem right now — ephemeral, stores nothing. Returns a
    dict: {activity, should_interject, confidence, reason, signals}. Neutral
    ('unknown', interject=True) when off/paused/unreadable, so Vera is unchanged."""
    neutral = {"activity": "unknown", "should_interject": True, "confidence": 0.0,
               "reason": "device sense off or unreadable", "signals": {}}
    if not _device_allowed():
        return neutral
    app, title = _frontmost()
    mic = mic_active()
    music_on = _music_playing()
    sig = {"app": app, "title": title[:120], "mic": mic, "music": music_on}
    is_browser = app in _BROWSERS

    def out(activity, interject, conf, reason):
        return {"activity": activity, "should_interject": interject,
                "confidence": conf, "reason": reason, "signals": sig}

    # 1) MEETING / CALL — strongest "hold back". Known app, or a meeting tab, or the
    # mic live alongside a comms/browser app.
    if app in _MEETING_APPS or (is_browser and _tab_hits(title, _MEETING_TABS)):
        return (out("meeting", False, 0.95, f"{app} with the mic live — you're in a call")
                if mic else out("meeting", False, 0.7, f"{app} is in front — a call may be running"))
    if mic and (is_browser or app in _COMMS_APPS):
        return out("call", False, 0.75, "your mic is live — sounds like you're talking to someone")
    if mic:
        return out("call", False, 0.55, "your mic is live — I'll wait")
    # 2) VIDEO — you're watching; keep it short (but don't go silent)
    if app in _VIDEO_APPS or (is_browser and _tab_hits(title, _VIDEO_TABS)):
        return out("video", True, 0.7, "you're watching something — I'll keep it brief")
    # 3) MUSIC — ambient; fine to talk
    if music_on:
        return out("music", True, 0.6, "music's on — just ambient")
    # 4) WORK — an app in front, nothing special
    if app:
        return out("work", True, 0.4, f"heads-down in {app}")
    return neutral


def _device_context() -> str:
    """The system-prompt line for the device ecosystem — ONLY when the moment calls
    for restraint (a call/meeting, or a video). Empty otherwise, so ordinary turns
    are unchanged. Reactive only: it shapes HOW she replies, never makes her speak."""
    if not _device_allowed():
        return ""
    d = device_now()
    act, conf = d["activity"], d["confidence"]
    if act in ("meeting", "call") and conf >= 0.55:
        return ("Right now they appear to be in a call or meeting (their mic is live / a "
                "meeting app is in front, measured on-device). Keep any reply very short "
                "and low-key, or just acknowledge and offer to pick it up after — do not "
                "launch into anything, and never assume they were talking to you unless "
                "they clearly addressed you.")
    if act == "video" and conf >= 0.6:
        return ("Right now they're watching something (measured on-device). Keep replies "
                "brief so you don't pull their attention away.")
    return ""


def context_for_prompt() -> str:
    """Honest lines for the system prompt — empty when she can't sense you.
    Composes whichever opt-in senses are live: the eye (face cues), the ear
    (ambient sound types), and the device sense (the ecosystem around the moment)."""
    parts = []
    face = _face_context()
    if face:
        parts.append(face)
    amb = ambient_current()
    if amb and (amb["sounds"] or amb["loud"] >= 0.12):
        names = ", ".join(s["label"] for s in amb["sounds"]) or "unclassified sound"
        parts.append("Around them (ambient sound, opt-in, on-device): "
                     f"{names} — a {_loud_word(amb['loud'])} room. Sound types "
                     "only, never recordings.")
    dev = _device_context()
    if dev:
        parts.append(dev)
    return " ".join(parts)


def _face_context() -> str:
    c = current()
    if not c or not c.get("present"):
        return ""
    bits = [_energy_word(c["energy"])]
    if (c.get("smile") or 0) >= 0.55:
        bits.append("smiling")
    if (c.get("brow") or 0) >= 0.55:
        bits.append("brow knitted")
    if (c.get("frown") or 0) >= 0.55 and (c.get("smile") or 0) < 0.55:
        bits.append("mouth downturned")
    if (c.get("blink_rate") or 0) >= 28:
        bits.append("blinking fast")
    if c.get("attending") is False:
        bits.append("looking away from the screen")
    if c.get("gesture") == "nod":
        bits.append("just nodded")
    elif c.get("gesture") == "shake":
        bits.append("just shook their head")
    if c.get("lean") == "in":
        bits.append("leaning in")
    elif c.get("lean") == "out":
        bits.append("leaning back")
    kind = "face cues" if c.get("source") == "face" else "motion cues"
    # READING THE ROOM: how many people, and whether this moment is likely
    # directed at her. This is what lets her hold back in a group instead of
    # answering chatter meant for someone else.
    room_line = ""
    people = c.get("people")
    if isinstance(people, int):
        if people == 0:
            room_line = " No one is in view right now."
        elif people == 1:
            if c.get("addressing_her") is False:
                room_line = (" It's just the two of you, but they're turned away — "
                             "this may not be meant for you; answer lightly, or wait.")
            else:
                room_line = " It's just the two of you — they're with you."
        else:  # 2+
            att = c.get("people_attending") or 0
            if not c.get("addressing_her"):
                room_line = (f" There are {people} people here and none are looking your "
                             "way — this is likely them talking to each other, not to you. "
                             "Stay quiet unless clearly addressed.")
            else:
                room_line = (f" There are {people} people here, {att} looking toward you — "
                             "you're in a group, so only respond to what's clearly meant "
                             "for you, and keep it brief and aware of the others.")
    # FEELING OVER TIME: the arc across the last ~30s, when it's actually moving.
    # This is the part that lets her meet a SHIFT ("you seem to be winding down")
    # rather than only the frozen frame — still measured, never a claimed feeling.
    trend = c.get("trend")
    trend_line = ""
    if trend:
        trend_line = (f" Over the last little while their expression has been "
                      f"{trend} (a measured trend, not a claimed feeling) — you may "
                      f"gently meet the shift if it fits, without naming it clinically.")
    return ("Right now you can see the user (their camera, on-device, opt-in): "
            "they look " + ", ".join(bits) + f". These are measured {kind} only — "
            "respond naturally, never claim to know their feelings from this."
            + trend_line + room_line)


def status() -> str:
    c = current()
    cam = (f"seeing you — {_energy_word(c['energy'])}" if c else "camera off")
    if device_enabled():
        d = device_now()
        dev = (f"device: {d['activity']} (conf {d['confidence']:.2f}) — {d['reason']}"
               f"{', holding back' if not d['should_interject'] else ''}")
    else:
        dev = "device: off"
    return f"presence: {cam} · {dev} · stores nothing"


def device_status() -> str:
    if not device_enabled():
        return ("device sense: off. Reads what you're doing right now (call / video / "
                "music / work) to know when to hold back — on-device, stores nothing. "
                "Turn on: python3 -m cognitive_twin.presence device on")
    d = device_now()
    return (f"device sense: on. Right now: {d['activity']} (confidence {d['confidence']:.2f}) "
            f"— {d['reason']}. {'holding back' if not d['should_interject'] else 'free to talk'}. "
            f"Stores nothing.")


# ── CLI ───────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(status()); return 0
    if cmd == "device":
        sub = argv[1] if len(argv) > 1 else "status"
        if sub in ("on", "enable"):
            enable_device(); print("✓ Device sense on (opt-in). Reads the moment, stores nothing."); return 0
        if sub in ("off", "disable"):
            disable_device(); print("✓ Device sense off."); return 0
        if sub == "now":
            d = device_now()
            print(f"{d['activity']} (confidence {d['confidence']:.2f}) — {d['reason']}")
            print(f"  hold back: {not d['should_interject']} · signals: {d['signals']}")
            return 0
        print(device_status()); return 0
    print("usage: python3 -m cognitive_twin.presence [status | device [on|off|now|status]]")
    return 2


if __name__ == "__main__":
    import sys as _sys
    raise SystemExit(_main(_sys.argv[1:]))
