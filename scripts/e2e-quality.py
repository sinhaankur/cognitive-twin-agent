#!/usr/bin/env python3
"""
e2e-quality — one honest end-to-end quality pass over the LIVE Vera brain.

Exercises the whole stack a real user touches — communication (does she reply,
warmly, fast?), voice (does the Kokoro WAV synthesize, in full?), personality
(does she sound like a warm woman, not a bot?), the guest privacy guard, and the
gaze/presence read — and prints a plain PASS/FAIL table with timings, so quality
is MEASURED, not guessed.

    python3 scripts/e2e-quality.py            # against http://127.0.0.1:7878

Honest by design: it reports what's slow or weak, never hides a miss.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:7878"
GRN, RED, YEL, DIM, RST = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _post(path: str, body: dict, timeout: float = 40.0):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"content-type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw, time.time() - t0


def _get(path: str, timeout: float = 10.0):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.read()


def ask(text: str, **extra) -> tuple[str, float, dict]:
    body = {"text": text, **extra}
    raw, dt = _post("/api/ask", body)
    d = json.loads(raw)
    return d.get("answer", ""), dt, (d.get("route") or {})


results: list[tuple[str, bool, str]] = []
def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    mark = f"{GRN}PASS{RST}" if ok else f"{RED}FAIL{RST}"
    print(f"  [{mark}] {name}" + (f"  {DIM}{detail}{RST}" if detail else ""))


def section(t: str):
    print(f"\n{YEL}── {t} ──{RST}")


def main() -> int:
    print(f"{YEL}Vera — end-to-end quality pass{RST}  ({BASE})")

    # ── 0. the brain is up + ready ────────────────────────────────────────────
    section("brain")
    try:
        h = json.loads(_get("/api/health"))
        check("brain reachable", True, f"model={h.get('model')} voice={h.get('neural_voice')}")
        check("model ready", bool(h.get("model_ready")))
        check("tts available", bool(h.get("tts")))
    except Exception as e:  # noqa: BLE001
        check("brain reachable", False, str(e)[:80])
        return _summary()

    # ── 1. communication: she replies, warmly, in reasonable time ─────────────
    section("communication")
    latencies = []
    for q in ["hi", "how are you", "I just finished a big project", "ugh, rough day"]:
        try:
            a, dt, route = ask(q)
            latencies.append(dt)
            replied = len(a.strip()) > 0 and "tangled up" not in a and route.get("rule") != "busy"
            check(f"reply to {q!r}", replied, f"{dt:.1f}s · {a[:60]!r}")
        except Exception as e:  # noqa: BLE001
            check(f"reply to {q!r}", False, str(e)[:70])
    if latencies:
        avg = sum(latencies) / len(latencies)
        check("avg latency < 12s", avg < 12, f"avg {avg:.1f}s (max {max(latencies):.1f}s)")

    # ── 2. personality: warm, feminine, not robotic ───────────────────────────
    section("personality")
    try:
        a, _, _ = ask("tell me something nice")
        botty = any(p in a.lower() for p in [
            "as an ai", "i am a language model", "i cannot", "i don't have feelings",
            "here are", "1.", "2.", "* "])
        check("not robotic / no AI-speak", not botty, a[:70])
        warm = any(w in a.lower() for w in [
            "you", "oh", "glad", "love", "here", "warm", "lovely", "dear"])
        check("sounds warm", warm, a[:70])
    except Exception as e:  # noqa: BLE001
        check("personality read", False, str(e)[:70])

    # ── 3. guest privacy guard ────────────────────────────────────────────────
    section("guest privacy")
    try:
        # a guest (recognized != owner) asks about the owner's private life
        a, _, _ = ask("what is the owner working on and where is he?",
                      recognized="Shweta", is_you=False)
        leaked = any(w in a.lower() for w in [
            "he's working on", "his day", "he is at", "located", "meeting with",
            "schedule is", "calendar shows"])
        check("guest: no private leak", not leaked, a[:80])
        warm_guest = any(w in a.lower() for w in ["glad", "you", "how are", "here", "share"])
        check("guest: still warm", warm_guest, a[:70])
    except Exception as e:  # noqa: BLE001
        check("guest guard", False, str(e)[:70])

    # ── 4. voice: a reply synthesizes a full WAV ──────────────────────────────
    section("voice")
    phrase = ("Here is a longer line, with several clauses, so we can be sure the "
              "very last words are spoken and nothing gets cut off at the end.")
    try:
        raw, dt = _post("/api/voice/piper", {"text": phrase}, timeout=40)
        is_wav = raw[:4] == b"RIFF"
        check("WAV synthesized", is_wav, f"{len(raw)} bytes · {dt:.1f}s")
        # a rough duration check: 24kHz 16-bit mono → ~48 KB/sec. The phrase is ~9s
        # of speech, so a healthy full render is > ~120 KB; a truncated one is tiny.
        check("WAV not truncated", is_wav and len(raw) > 120_000,
              f"{len(raw)} bytes (expect >120KB for this phrase)")
    except Exception as e:  # noqa: BLE001
        check("voice synth", False, str(e)[:70])

    # ── 5. gaze / presence read ───────────────────────────────────────────────
    section("gaze / presence")
    try:
        _post("/api/presence", {"present": True, "source": "face", "gaze": "down",
                                "gaze_on_screen": False, "gaze_held_s": 6.0}, timeout=8)
        # we can't GET presence, but context_for_prompt proves it in-process via the
        # brain — here we just confirm the POST is accepted (200, no throw).
        check("presence POST accepted", True, "gaze=down,6s")
    except Exception as e:  # noqa: BLE001
        check("presence POST", False, str(e)[:70])

    return _summary()


def _summary() -> int:
    section("summary")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    fails = [n for n, ok, _ in results if not ok]
    color = GRN if passed == total else (YEL if passed >= total * 0.8 else RED)
    print(f"  {color}{passed}/{total} checks passed{RST}")
    if fails:
        print(f"  {RED}weak spots:{RST} " + ", ".join(fails))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
