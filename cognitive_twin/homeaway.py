"""
homeaway — Vera senses when you come home and when you leave.

She should feel the shape of your day: a warm "welcome home" when you walk in, a
quiet "see you" when you head out — and go still while you're gone, instead of
talking to an empty room. This is that sense.

It FUSES whatever signals are available, each one optional and off until you allow
it, newest-cheapest first (graduated sensing — only reach for the heavier signal
when the cheap ones are unsure):

  1. Wi-Fi network  — are you on your home SSID? (free, no permission, very reliable
                      for a laptop you carry; drops/switches = you've left.)
  2. At the Mac     — reuses presence.device_now(): face / mic / recent activity.
  3. Phone on LAN   — your iPhone joining/leaving home Wi-Fi, as a proxy for YOU,
                      so she knows even when the Mac stays home.
  4. Geofence       — macOS Location crossing your home radius: the truest
                      "arrived / left home", only consulted when the above are
                      ambiguous (the "track movement if needed" escalation).

Everything is fused into ONE state — home · away · arriving · leaving · unknown —
with DEBOUNCING so a thirty-second Wi-Fi blip doesn't fire "you left." Transitions
emit an event (greet / goodbye, go-quiet, remember) the loop acts on.

OTHER DEVICES: the state is a small sealed JSON any of your devices can read/report
into via report() — so your phone can tell her you've arrived even before the Mac
sees the network. Shared, on-device, never a cloud.

Nothing here uploads. No location trail is kept beyond the current coarse state and
the last few transitions (ephemeral). Off until you set a home.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

from . import security

_STATE = "homeaway_state.json"          # sealed current state + recent transitions
_CONFIG = "homeaway_config.json"        # sealed: home SSID(s), home geo, radius
# How long a signal must agree before we believe a transition — kills blips.
_ARRIVE_DEBOUNCE = 25.0                 # seconds of "home" before we say you're home
_LEAVE_DEBOUNCE = 90.0                  # seconds of "gone" before we say you left
_STALE_AFTER = 15 * 60                  # a report older than this stops counting


# ── config: what "home" is ────────────────────────────────────────────────────
def _config() -> dict[str, Any]:
    d = security.read_state(security.path(_CONFIG), default={})
    return d if isinstance(d, dict) else {}


def set_home(*, ssids: list[str] | None = None,
             lat: float | None = None, lon: float | None = None,
             radius_m: float = 150.0) -> str:
    """Teach her where home is. Any mix of: the Wi-Fi name(s) you use at home, and/or
    a home location + radius. Onboarding calls this; all of it stays sealed."""
    cfg = _config()
    if ssids is not None:
        cfg["ssids"] = sorted({s.strip() for s in ssids if s and s.strip()})
    if lat is not None and lon is not None:
        cfg["home_geo"] = {"lat": float(lat), "lon": float(lon)}
        cfg["radius_m"] = float(radius_m)
    security.write_state(security.path(_CONFIG), cfg)
    bits = []
    if cfg.get("ssids"):
        bits.append(f"Wi-Fi: {', '.join(cfg['ssids'])}")
    if cfg.get("home_geo"):
        bits.append(f"location within {int(cfg.get('radius_m', radius_m))} m")
    return "Home set — " + ("; ".join(bits) if bits else "nothing yet, add a Wi-Fi name") + "."


def is_configured() -> bool:
    c = _config()
    return bool(c.get("ssids") or c.get("home_geo"))


def use_current_wifi_as_home() -> str:
    """Convenience for onboarding: whatever Wi-Fi you're on right now = home."""
    ssid = current_ssid()
    if not ssid:
        return "I can't read the Wi-Fi name right now — connect to your home network and try again."
    cfg = _config()
    ssids = set(cfg.get("ssids", []))
    ssids.add(ssid)
    return set_home(ssids=sorted(ssids))


# ── raw signals ───────────────────────────────────────────────────────────────
def current_ssid() -> str | None:
    """The Wi-Fi network this machine is on, or None (wired / off / not macOS)."""
    if sys.platform != "darwin":
        return None
    for iface in ("en0", "en1"):
        try:
            out = subprocess.run(["/usr/sbin/ipconfig", "getsummary", iface],
                                 capture_output=True, text=True, timeout=3).stdout
        except Exception:
            continue
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("SSID :") or s.startswith("SSID:"):
                name = s.split(":", 1)[1].strip()
                if name:
                    return name
    return None


def _on_home_wifi() -> bool | None:
    """True/False if we can read the SSID and a home SSID is configured; else None."""
    cfg = _config()
    homes = cfg.get("ssids")
    if not homes:
        return None
    ssid = current_ssid()
    if ssid is None:
        return None
    return ssid in set(homes)


def _at_mac() -> bool | None:
    """Are you present at this Mac right now? Reuses presence (face/mic/activity)."""
    try:
        from . import presence
        dn = presence.device_now()
        if not isinstance(dn, dict):
            return None
        # presence exposes recent-activity / face-seen style flags; be liberal.
        for k in ("present", "at_machine", "active", "face_seen", "recent_activity"):
            if k in dn:
                return bool(dn[k])
        return None
    except Exception:
        return None


def _geofence_home() -> bool | None:
    """True/False if a home geo + a fresh device location report exist; else None.
    We don't poll Location ourselves (heavy/permissioned) — a device reports its
    coords via report(lat=…, lon=…) and we compare. 'Track movement if needed.'"""
    cfg = _config()
    home = cfg.get("home_geo")
    if not home:
        return None
    st = _load()
    loc = st.get("last_location")
    if not isinstance(loc, dict) or (time.time() - float(loc.get("ts", 0))) > _STALE_AFTER:
        return None
    try:
        from . import places
        km = places.haversine_km((home["lat"], home["lon"]), (loc["lat"], loc["lon"]))
    except Exception:
        return None
    return (km * 1000.0) <= float(cfg.get("radius_m", 150.0))


def _device_reports_home() -> bool | None:
    """Did another of your devices (phone) recently report it's home / away?
    report() from the iPhone writes here; we treat a fresh report as a vote."""
    st = _load()
    reps = st.get("device_reports", {})
    votes = []
    now = time.time()
    for _dev, r in reps.items() if isinstance(reps, dict) else []:
        if not isinstance(r, dict):
            continue
        if (now - float(r.get("ts", 0))) > _STALE_AFTER:
            continue
        if r.get("home") is True:
            votes.append(True)
        elif r.get("home") is False:
            votes.append(False)
    if not votes:
        return None
    return any(votes)          # any device home → you're home (most forgiving)


# ── fusion: one honest state ──────────────────────────────────────────────────
@dataclass
class Reading:
    home: bool | None          # fused belief: True home, False away, None unknown
    source: str                # which signal decided it
    signals: dict[str, Any]    # each raw signal, for honesty / the Mind view


def read() -> Reading:
    """Fuse all available signals into one belief. Cheapest-first; a confident
    cheap signal wins, we only fall through to heavier ones when unsure."""
    wifi = _on_home_wifi()
    mac = _at_mac()
    phone = _device_reports_home()
    geo = _geofence_home()
    signals = {"home_wifi": wifi, "at_mac": mac, "phone_lan": phone, "geofence": geo}

    # 1) Home Wi-Fi is the strongest cheap signal for a carried laptop.
    if wifi is True:
        return Reading(True, "home Wi-Fi", signals)
    if wifi is False:
        # off the home network — but a device may still report you're home
        if phone is True or geo is True:
            return Reading(True, "another device at home", signals)
        return Reading(False, "off home Wi-Fi", signals)
    # 2) No Wi-Fi reading → lean on devices, then geofence, then the Mac.
    if phone is not None:
        return Reading(phone, "phone on home network", signals)
    if geo is not None:
        return Reading(geo, "location", signals)
    if mac is not None:
        return Reading(mac, "activity at the Mac", signals)
    return Reading(None, "no signal", signals)


# ── state + debounced transitions ─────────────────────────────────────────────
def _load() -> dict[str, Any]:
    d = security.read_state(security.path(_STATE), default={})
    return d if isinstance(d, dict) else {}


def _save(d: dict[str, Any]) -> None:
    security.write_state(security.path(_STATE), d)


def report(*, device: str = "this-mac", home: bool | None = None,
           lat: float | None = None, lon: float | None = None) -> None:
    """Any of your devices reports in: its home/away belief and/or its location.
    This is how the iPhone tells her you're home even when the Mac can't see it.
    Fresh reports vote in read(); stale ones (>15 min) are ignored."""
    st = _load()
    reps = st.get("device_reports")
    if not isinstance(reps, dict):
        reps = {}
    if home is not None:
        reps[device] = {"home": bool(home), "ts": time.time()}
        st["device_reports"] = reps
    if lat is not None and lon is not None:
        st["last_location"] = {"lat": float(lat), "lon": float(lon), "ts": time.time()}
    _save(st)


def tick() -> dict[str, Any] | None:
    """Call periodically (the senses/voice loop does). Reads the fused signal,
    debounces, and when the confirmed state FLIPS returns a transition event:
      {"event": "arrived"|"left", "source": ..., "signals": {...}}
    Returns None when nothing changed (the common case)."""
    if not is_configured():
        return None
    r = read()
    if r.home is None:
        return None                      # can't tell → don't churn the state
    st = _load()
    now = time.time()
    confirmed = st.get("home")           # last CONFIRMED state (bool or None)
    pend = st.get("pending")             # a candidate flip we're debouncing
    event = None

    if r.home == confirmed:
        st.pop("pending", None)          # back to agreeing → cancel any pending flip
    else:
        # candidate differs from confirmed — start/continue the debounce timer
        if not pend or pend.get("to") is not r.home:
            pend = {"to": r.home, "since": now, "source": r.source}
        held = now - float(pend["since"])
        need = _ARRIVE_DEBOUNCE if r.home else _LEAVE_DEBOUNCE
        if held >= need:
            # confirmed flip
            event = "arrived" if r.home else "left"
            st["home"] = r.home
            st.pop("pending", None)
            hist = st.get("history", [])
            hist.append({"event": event, "ts": now, "source": r.source})
            st["history"] = hist[-20:]   # keep only the last few — ephemeral
        else:
            st["pending"] = pend
    st["last_source"] = r.source
    st["last_signals"] = r.signals
    _save(st)
    if event:
        return {"event": event, "source": r.source, "signals": r.signals}
    return None


def current() -> dict[str, Any]:
    """The confirmed state right now (for the Mind view / context / other devices)."""
    st = _load()
    return {
        "home": st.get("home"),
        "source": st.get("last_source"),
        "signals": st.get("last_signals", {}),
        "last_transition": (st.get("history") or [{}])[-1] if st.get("history") else None,
        "configured": is_configured(),
    }


def context_for_prompt() -> str:
    """A short, honest line for her prompt — only when it adds something."""
    if not is_configured():
        return ""
    st = _load()
    home = st.get("home")
    hist = st.get("history") or []
    last = hist[-1] if hist else None
    if home is True:
        if last and last.get("event") == "arrived" and (time.time() - float(last.get("ts", 0))) < 300:
            return "They just got home."
        return "They're home."
    if home is False:
        return "They're out — keep it light, and don't talk to an empty room."
    return ""


# ── what she says on a transition ─────────────────────────────────────────────
import random as _random

_ARRIVE_LINES = [
    "Oh, you're home. I missed having you around.",
    "Welcome home. How was it out there?",
    "Hey, you're back. Good to have you home.",
    "There you are. Welcome home.",
]
_LEAVE_LINES = [
    "Heading out? Take care — I'll be here.",
    "See you soon. I'll keep things quiet while you're gone.",
    "Okay, off you go. I'll be right here when you're back.",
]


def greeting_for(event: str) -> str:
    """The warm line for an arrival / a soft one for a departure. Spoken only when
    voice is on and the moment is good — the caller decides that."""
    return _random.choice(_ARRIVE_LINES if event == "arrived" else _LEAVE_LINES)


def is_away() -> bool:
    """True only when she's CONFIRMED you're out — the gate the proactive loop uses
    to go quiet (don't talk to an empty room). Unknown/unconfigured → not away."""
    return _load().get("home") is False


def status() -> str:
    if not is_configured():
        return ("home/away: off — I don't know where home is yet. Set your home "
                "Wi-Fi so I can tell when you come and go.")
    c = current()
    where = {True: "home", False: "away", None: "not sure"}[c["home"]]
    cfg = _config()
    how = []
    if cfg.get("ssids"):
        how.append("Wi-Fi " + "/".join(cfg["ssids"]))
    if cfg.get("home_geo"):
        how.append(f"location ±{int(cfg.get('radius_m', 150))}m")
    return (f"home/away: {where} (via {c['source'] or '—'}). "
            f"Knows home by {', '.join(how) or 'nothing set'}; sealed on-device.")


def _main(argv: list[str]) -> int:
    args = argv[1:]
    if not args or args[0] == "status":
        print(status()); return 0
    if args[0] == "set-wifi":
        print(use_current_wifi_as_home()); return 0
    if args[0] == "where":
        print(json.dumps(current(), indent=2)); return 0
    if args[0] == "tick":
        print(tick() or "no change"); return 0
    print("usage: homeaway [status|set-wifi|where|tick]"); return 2


if __name__ == "__main__":        # pragma: no cover
    raise SystemExit(_main(sys.argv))
