"""
Vera diagnostics — a day-to-day health report you can actually act on.

Run it, see what's working, and (because it logs every run) watch how that
changes over days. Built for the intermittent problems that one-shot checks miss:
"the mic works at times and sometimes it doesn't" only becomes visible as a
PATTERN across runs, so every run appends one line to a dated log and `trends()`
summarises reliability ("mic: 7/10 ok").

It SIMULATES real usage rather than only inspecting flags: it asks the LLM a real
prompt, pushes a synthetic clip through the transcribe pipeline, builds the real
opener — so a green line means the path actually worked end to end, not just that
a module imported.

Every check is wrapped: a subsystem being absent, a model being down, or a raised
exception becomes a ✗ line with the reason — the report never crashes. Same
(ok, label, detail) shape as `security.doctor()`, so output + logging are uniform.

Pure stdlib. No new dependencies. Safe to run with the brain up or down.
"""

from __future__ import annotations

import io
import json
import math
import struct
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

Check = tuple[bool, str, str]   # (ok, label, detail) — same shape as security.doctor

_BRAIN = "http://127.0.0.1:7878"
_LOG = Path.home() / "Library" / "Logs" / "Vera" / "diagnostics.jsonl"
_LOG_MAX_BYTES = 2_000_000      # ~ tens of thousands of runs; rotate past this


# ── helpers ──────────────────────────────────────────────────────────────────

def _guard(fn: Callable[[], Check]) -> Check:
    """Run a check; turn any raise into a ✗ line so the report never dies."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 — a diagnostic must survive anything
        return (False, getattr(fn, "_label", fn.__name__), f"errored: {e}")


def _get(path: str, timeout: float = 6.0) -> tuple[int, bytes]:
    req = urllib.request.Request(_BRAIN + path)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def _post(path: str, body: bytes, ctype: str, timeout: float = 45.0) -> tuple[int, bytes]:
    req = urllib.request.Request(_BRAIN + path, data=body, method="POST")
    req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def _tone_wav(seconds: float = 1.0, hz: float = 220.0, sr: int = 16_000) -> bytes:
    """A tiny 16k mono PCM16 WAV — a synthetic 'utterance' to exercise the STT
    pipeline without a microphone. Proves the software path works even when the
    physical mic is silent (so we can tell 'software broke' from 'mic/gain')."""
    n = int(sr * seconds)
    data = b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * hz * i / sr))) for i in range(n))
    b = io.BytesIO()
    b.write(b"RIFF"); b.write(struct.pack("<I", 36 + len(data))); b.write(b"WAVE")
    b.write(b"fmt "); b.write(struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16))
    b.write(b"data"); b.write(struct.pack("<I", len(data))); b.write(data)
    return b.getvalue()


# ── section: the week's breakages (SIMULATED end-to-end) ──────────────────────

def check_core() -> list[Check]:
    out: list[Check] = []

    # brain reachable
    def brain() -> Check:
        t0 = time.time()
        code, raw = _get("/api/health", timeout=4)
        ms = int((time.time() - t0) * 1000)
        info = json.loads(raw or b"{}")
        ok = code == 200 and info.get("ok") is True
        return (ok, "brain reachable", f"{_BRAIN} · {ms}ms · model={info.get('model','?')}")
    out.append(_guard(brain))

    # LLM actually answers (simulated turn)
    def llm() -> Check:
        body = json.dumps({"text": "Reply with the single word READY."}).encode()
        code, raw = _post("/api/ask", body, "application/json", timeout=45)
        ans = (json.loads(raw or b"{}").get("answer") or "").strip()
        ok = code == 200 and len(ans) > 0
        return (ok, "LLM answers", (f'said: "{ans[:60]}"' if ans else "empty answer — model not really responding"))
    out.append(_guard(llm))

    # voice ready + the ONE locked voice (af_heart)
    def voice() -> Check:
        from .voice import kokoro_tts
        vs = kokoro_tts.voice_state()
        state = vs.get("state", "?")
        voice_name = vs.get("voice", "?")
        ok = state == "ready"
        detail = f"{state} · voice={voice_name}"
        if ok and voice_name not in ("", "af_heart", "kokoro"):
            detail += " (NOTE: not af_heart — the locked default)"
        return (ok, "voice (Kokoro)", detail)
    out.append(_guard(voice))

    # mic / transcribe pipeline (synthetic clip — software path, not the hardware)
    def mic() -> Check:
        code, raw = _post("/api/transcribe", _tone_wav(), "audio/wav", timeout=30)
        obj = json.loads(raw or b"{}")
        well_formed = code == 200 and "heard" in obj and "text" in obj
        return (well_formed, "mic/transcribe pipeline",
                f"endpoint ok · heard={obj.get('heard')} (synthetic clip; proves the SOFTWARE path — not the mic gain)")
    out.append(_guard(mic))

    # camera / presence (can't force TCC; report honestly)
    def camera() -> Check:
        from . import presence
        cur = presence.current()
        if cur is None:
            return (True, "camera/presence", "off or idle (no recent reading — not an error)")
        return (True, "camera/presence", f"seeing you · people={cur.get('people','?')}")
    out.append(_guard(camera))

    # opener is CLEAN (warm greeting, no garbage nudge)
    def opener() -> Check:
        from .skills import builtin
        from . import shadow
        greet = builtin.greeting()
        tasks = shadow.opener_tasks()
        cold = greet.startswith("Good ") and "°C" in greet and "—" not in greet.split("°C")[0]
        warm = not cold and len(greet) > 0
        return (warm, "opener clean",
                f'"{greet[:70]}" · nudge-tasks={len(tasks)} (trusted only)')
    out.append(_guard(opener))

    return out


# ── section: subsystem status() roundup ──────────────────────────────────────

_SUBSYSTEMS = [
    "memory", "places", "music", "presence", "persona",
    "health", "rhythms", "soul", "mental_model", "media",
]


def check_subsystems() -> list[Check]:
    out: list[Check] = []
    for name in _SUBSYSTEMS:
        def one(name: str = name) -> Check:
            mod = __import__(f"cognitive_twin.{name}", fromlist=["status"])
            text = str(mod.status()).strip().replace("\n", " ")
            return (True, f"status · {name}", text[:90] or "(empty)")
        out.append(_guard(one))
    return out


# ── section: security doctor (folded in) ──────────────────────────────────────

def check_security() -> list[Check]:
    try:
        from . import security
        _safe, checks = security.doctor()
        return [(ok, f"security · {label}", detail) for ok, label, detail in checks]
    except Exception as e:  # noqa: BLE001
        return [(False, "security · doctor", f"errored: {e}")]


# ── section: performance (CPU / RAM at report time) ───────────────────────────

def _proc_stats(pattern: str) -> tuple[float, float] | None:
    """(%cpu, rss_mb) for the first process whose command matches `pattern`."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,%cpu=,rss=,command="],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    for line in out.splitlines():
        if pattern in line and "grep" not in line:
            parts = line.split(None, 3)
            if len(parts) >= 3:
                try:
                    return float(parts[1]), float(parts[2]) / 1024.0
                except ValueError:
                    continue
    return None


def check_performance() -> list[Check]:
    out: list[Check] = []
    brain = _proc_stats("cognitive_twin.voice.server") or _proc_stats("vera-brain")
    app = _proc_stats("Vera.app/Contents/MacOS/Vera")
    if brain:
        cpu, rss = brain
        out.append((cpu < 80, "perf · brain", f"cpu={cpu:.0f}% rss={rss:.0f}MB"))
    else:
        out.append((True, "perf · brain", "not running"))
    if app:
        cpu, rss = app
        # the app idling hot is a real day-to-day annoyance → flag above 35%
        out.append((cpu < 35, "perf · app", f"cpu={cpu:.0f}% rss={rss:.0f}MB"))
    else:
        out.append((True, "perf · app", "not running"))
    return out


# ── the report ────────────────────────────────────────────────────────────────

@dataclass
class Report:
    ts: str
    sections: dict[str, list[Check]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(ok for checks in self.sections.values() for ok, _, _ in checks)

    def _flat(self) -> list[Check]:
        return [c for checks in self.sections.values() for c in checks]

    def render(self) -> str:
        lines = [f"Vera diagnostics — {self.ts}", ""]
        for title, checks in self.sections.items():
            lines.append(f"  {title.upper()}")
            for ok, label, detail in checks:
                lines.append(f"    {'✓' if ok else '✗'} {label:<26} {detail}")
            lines.append("")
        failures = [label for ok, label, _ in self._flat() if not ok]
        if failures:
            lines.append(f"✗ {len(failures)} issue(s): " + ", ".join(failures))
        else:
            lines.append("✓ all green — everything checked is working.")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "ok": self.ok,
            "sections": {
                title: [{"ok": ok, "label": label, "detail": detail} for ok, label, detail in checks]
                for title, checks in self.sections.items()
            },
        }

    def log_line(self) -> dict[str, Any]:
        """The compact line appended to the day-to-day log. Flags the subsystems we
        care about tracking (so trends() can compute reliability fast)."""
        def found(substr: str) -> bool | None:
            for ok, label, _ in self._flat():
                if substr in label:
                    return ok
            return None
        perf = {label: detail for ok, label, detail in self.sections.get("performance", [])}
        return {
            "ts": self.ts,
            "ok": self.ok,
            "brain_ok": found("brain reachable"),
            "llm_ok": found("LLM answers"),
            "voice_ok": found("voice (Kokoro)"),
            "mic_ok": found("mic/transcribe"),
            "opener_ok": found("opener clean"),
            "cpu_brain": perf.get("perf · brain", ""),
            "cpu_app": perf.get("perf · app", ""),
            "failures": [label for ok, label, _ in self._flat() if not ok],
        }


def run(log: bool = True) -> Report:
    """Run every section and (by default) append one line to the day-to-day log."""
    rep = Report(ts=datetime.now().isoformat(timespec="seconds"))
    rep.sections["core"] = check_core()
    rep.sections["subsystems"] = check_subsystems()
    rep.sections["security"] = check_security()
    rep.sections["performance"] = check_performance()
    if log:
        _append_log(rep.log_line())
    return rep


# ── the day-to-day log + trends ───────────────────────────────────────────────

def _append_log(line: dict[str, Any]) -> None:
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        if _LOG.exists() and _LOG.stat().st_size > _LOG_MAX_BYTES:
            # keep the most recent half — a rolling window, never unbounded
            tail = _LOG.read_text(encoding="utf-8").splitlines()[-2000:]
            _LOG.write_text("\n".join(tail) + "\n", encoding="utf-8")
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception:  # noqa: BLE001 — logging must never break a run
        pass


def _read_log(n: int | None = None) -> list[dict[str, Any]]:
    if not _LOG.exists():
        return []
    rows = []
    for ln in _LOG.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows[-n:] if n else rows


def trends(n: int = 14) -> str:
    """Reliability over the last N runs — the day-to-day value. Catches the flaky
    stuff ('mic: 7/10 ok') a single run can't."""
    rows = _read_log(n)
    if not rows:
        return "No diagnostics history yet. Run `diagnose` a few times."
    keys = [("brain_ok", "brain"), ("llm_ok", "LLM"), ("voice_ok", "voice"),
            ("mic_ok", "mic"), ("opener_ok", "opener")]
    lines = [f"Diagnostics trends — last {len(rows)} run(s) "
             f"({rows[0]['ts'][:16]} → {rows[-1]['ts'][:16]})", ""]
    for key, label in keys:
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        if not vals:
            lines.append(f"  {label:<8} no data")
            continue
        good = sum(1 for v in vals if v)
        flag = "" if good == len(vals) else ("  ⚠ FLAKY" if good else "  ✗ DOWN")
        lines.append(f"  {label:<8} {good}/{len(vals)} ok{flag}")
    # surface the most common failure
    all_fail: dict[str, int] = {}
    for r in rows:
        for f in r.get("failures", []):
            all_fail[f] = all_fail.get(f, 0) + 1
    if all_fail:
        worst = sorted(all_fail.items(), key=lambda kv: -kv[1])[:3]
        lines.append("")
        lines.append("  most frequent failures: " + ", ".join(f"{k} ({v}×)" for k, v in worst))
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _main(argv: list[str]) -> int:
    if argv and argv[0] == "--trends":
        print(trends(int(argv[1]) if len(argv) > 1 else 14))
        return 0
    rep = run()
    if argv and argv[0] == "--json":
        print(json.dumps(rep.as_dict(), indent=2))
    else:
        print(rep.render())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
