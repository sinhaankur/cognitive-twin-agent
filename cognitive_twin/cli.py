"""
Cognitive Twin CLI.

  ctwin "what's the date?"          one-shot
  ctwin                            interactive REPL
  ctwin --model qwen2.5 "..."      pick a model

Reads optional config from agent_config.json (model, host). Imports the built-in
skills so they're registered. Fails clearly if Ollama isn't running / the model
isn't pulled — no cloud fallback (this is local-first by design).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent.loop import Agent
from .agent.router import Router
from .llm.ollama_client import OllamaClient, OllamaError
from .llm.openai_client import OpenAIError
from .llm import providers

# Either backend can raise its own "brain unreachable / model missing" error.
LLM_ERRORS = (OllamaError, OpenAIError)
from . import skills  # noqa: F401  (registry exists)
from .skills import builtin  # noqa: F401  (registers built-in skills)
from .skills import vscode_drive  # noqa: F401  (registers VS Code drive skills)
from .skills.base import default_registry


def _load_config() -> dict:
    for p in (Path.cwd() / "agent_config.json", Path.cwd() / "agent_config.example.json"):
        try:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def build_agent(model: str | None = None, *, route: bool = True,
                interactive_confirm: bool = True) -> Agent:
    cfg = _load_config()
    model = (
        model
        or os.environ.get("CTWIN_MODEL")
        or cfg.get("model")
        or cfg.get("llm", {}).get("model")
        or "qwen2.5:7b"
    )
    host = os.environ.get("CTWIN_OLLAMA_HOST") or cfg.get("host") or "http://localhost:11434"

    # Multi-backend: Ollama plus an optional OpenAI-compatible server (LM Studio,
    # llama.cpp, Jan, …). The backend stays Ollama-only unless an OpenAI base is
    # configured, so default installs are unchanged.
    backend = providers.MultiBackend(
        ollama_host=host,
        openai_base=providers.openai_base_url(cfg),
        openai_label=providers.openai_label(cfg),
    )
    # Build the client for the configured model id; a `label/name` id selects the
    # OpenAI backend, a bare name selects Ollama.
    client = backend.client_for(model)
    # Policy-driven routing is on by default — pick a local model per request from
    # policies/model-routing.policy.json. An explicit --model or --no-route turns
    # it off and pins the one model. Routing only applies to Ollama models, so if
    # the pinned model is on the OpenAI backend, leave routing off.
    if route and backend.is_openai_model(model):
        route = False
    router = Router() if route else None
    # use_memory=True: the real app learns the user's patterns locally (private,
    # on-device). Tests construct Agent directly and leave it off.
    agent = Agent(client=client, registry=default_registry, router=router, use_memory=True)
    # Remember the configured default so fallback can prefer it over a random
    # installed model (which might not support tool-calling).
    agent.configured_model = model  # type: ignore[attr-defined]
    # Attach the backend so the voice server can discover models across providers
    # and switch the active client when the user picks a different one.
    agent.backend = backend  # type: ignore[attr-defined]
    # Screen-control actions confirm via an interactive y/N prompt — but only for
    # the terminal path. The voice server installs its own (non-blocking) confirm.
    if interactive_confirm:
        _install_confirm()
    return agent


# Model families known to support tool/function calling in Ollama. Used to pick a
# sane fallback when the policy's model isn't pulled. Not exhaustive — just a
# preference order over "first installed", which may be a tool-less tiny model.
_TOOL_CAPABLE_HINTS = ("qwen2.5", "qwen3", "llama3.1", "llama3.2", "mistral", "deepseek")


def _choose_fallback(configured: str | None, installed: list[str]) -> str | None:
    """Pick the best installed model to fall back to: the configured default if
    it's present, else a known tool-capable model, else the first installed."""
    if not installed:
        return None
    if configured:
        base = configured.split(":")[0]
        for m in installed:
            if m == configured or m.split(":")[0] == base:
                return m
    for hint in _TOOL_CAPABLE_HINTS:
        for m in installed:
            if m.split(":")[0].startswith(hint):
                return m
    return installed[0]


def _run_once(agent: Agent, prompt: str, explain: bool, *, repl: bool = False) -> bool:
    """Run one prompt. With routing on, if the routed model isn't pulled, pin an
    installed model for this run so the agent still answers — staying local.
    Prints the route when `explain` is set. Returns True on success."""
    suffix = "\n" if repl else ""
    client = agent.client
    pinned: str | None = None  # set when we fall back off the routed model

    if agent.router is not None and hasattr(client, "available_models"):
        decision = agent.router.route(prompt)
        installed = client.available_models()  # type: ignore[attr-defined]
        base = decision.model.split(":")[0]
        have = any(m == decision.model or m.split(":")[0] == base for m in installed)
        if not have and installed:
            configured = getattr(agent, "configured_model", None)
            pinned = _choose_fallback(configured, installed)
            if explain:
                print(
                    f"route · policy wanted {decision.model} ({decision.rule_id}); "
                    f"not pulled → using {pinned}",
                    file=sys.stderr,
                )
        elif explain:
            print(decision.explain(), file=sys.stderr)

    # If we're falling back, pin the model and turn routing off for this one run
    # (so agent.run doesn't re-route over our choice).
    saved_router = None
    if pinned is not None:
        client.model = pinned  # type: ignore[attr-defined]
        saved_router, agent.router = agent.router, None
    try:
        result = agent.run(prompt)
    except LLM_ERRORS as e:
        print(f"⚠ {e}{suffix}", file=sys.stderr)
        return False
    finally:
        if saved_router is not None:
            agent.router = saved_router

    print(result.answer + suffix)
    return True


def _run_once_capture(agent: Agent, prompt: str) -> tuple[str, dict | None]:
    """Run one prompt and RETURN (answer, route_dict) instead of printing — used
    by the voice server. Shares the routed-model fallback behaviour of _run_once
    (if the policy's model isn't pulled, pin a tool-capable installed one)."""
    client = agent.client
    pinned: str | None = None
    route_dict: dict | None = None

    if agent.router is not None and hasattr(client, "available_models"):
        decision = agent.router.route(prompt)
        installed = client.available_models()  # type: ignore[attr-defined]
        base = decision.model.split(":")[0]
        have = any(m == decision.model or m.split(":")[0] == base for m in installed)
        used_model = decision.model
        if not have and installed:
            configured = getattr(agent, "configured_model", None)
            pinned = _choose_fallback(configured, installed)
            used_model = pinned or decision.model
        route_dict = {
            "model": used_model,
            "policyModel": decision.model,
            "rule": decision.rule_id,
            "complexity": decision.task_complexity,
            "risk": decision.risk_level,
            "fellBack": pinned is not None,
        }

    saved_router = None
    if pinned is not None:
        client.model = pinned  # type: ignore[attr-defined]
        saved_router, agent.router = agent.router, None
    try:
        result = agent.run(prompt)
    finally:
        if saved_router is not None:
            agent.router = saved_router

    return result.answer, route_dict


def _reflect_once(*, quiet: bool = False) -> str | None:
    """Have the twin think about your projects once — while you're away — and
    save the thought for your next session. Returns the thought, or None.

    This is what makes the proactive opening *alive*: the "while you were away"
    line becomes a real, fresh thought the twin had, not a canned one. Runs the
    local model; silent + best-effort so it can be scheduled in the background.
    """
    from . import soul
    instruction = soul.reflection_prompt()
    if not instruction:
        if not quiet:
            print("  nothing to reflect on yet — talk with your twin a bit first.")
        return None
    try:
        agent = build_agent(None, route=True, interactive_confirm=False)
        client = agent.client
        if hasattr(client, "is_up") and not client.is_up():  # type: ignore[attr-defined]
            if not quiet:
                print("  (model offline — skipping this reflection)")
            return None
        thought, _ = _run_once_capture(agent, instruction)
    except LLM_ERRORS:
        return None
    except Exception:
        return None
    thought = (thought or "").strip()
    if not thought:
        return None
    soul.add_reflection(thought)
    if not quiet:
        print(f"  💭 {thought}")
    return thought


def _reflect_command(rest: list[str]) -> int:
    """`ctwin reflect [--watch [MINUTES]]` — think now, or keep thinking in the
    background (the 'JARVIS keeps working while you're away' loop)."""
    ra = argparse.ArgumentParser(prog="ctwin reflect")
    ra.add_argument("--watch", nargs="?", const=30, type=int, default=None,
                    metavar="MINUTES",
                    help="keep reflecting every N minutes (default 30) until stopped")
    args = ra.parse_args(rest)

    if args.watch is None:
        return 0 if _reflect_once() is not None else 0

    interval = max(1, args.watch) * 60
    print(f"  {_active_twin_name()} is thinking in the background "
          f"(every {args.watch} min). Ctrl-C to stop.\n")
    import time
    try:
        while True:
            t = _reflect_once(quiet=False)
            if t is None:
                print("  (waiting for something to think about…)")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  stopped. The thoughts I had are saved for next time. 🌅")
        return 0


def _viz_command(rest: list[str]) -> int:
    """`ctwin viz` — open the Visualize Engine: a local page that shows how the
    twin thinks (reasoning trace, knowledge graph, inner state) from real data.
    Reachable from the app's Settings ("How this works")."""
    za = argparse.ArgumentParser(prog="ctwin viz")
    za.add_argument("--port", type=int, default=7879)
    za.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    args = za.parse_args(rest)
    from . import viz
    try:
        viz.serve(args.port, open_browser=not args.no_open)
    except OSError as e:
        print(f"⚠ couldn't start the Visualize Engine: {e}", file=sys.stderr)
        return 1
    return 0


def _voice_command(rest: list[str]) -> int:
    """`ctwin voice` — launch the Siri-style voice UI. Default: native menubar
    (needs rumps); --web runs the browser version (no extra deps)."""
    va = argparse.ArgumentParser(prog="ctwin voice", description="Local Siri-style voice UI.")
    va.add_argument("--web", action="store_true", help="run the browser UI instead of the menubar")
    va.add_argument("--port", type=int, default=7878)
    va.add_argument("--no-open", action="store_true", help="(web) don't auto-open the browser")
    va.add_argument("--model", help="pin a model (otherwise policy routing chooses)")
    a = va.parse_args(rest)
    if a.web:
        from .voice.server import serve
        serve(a.port, open_browser=not a.no_open, model=a.model)
    else:
        from .voice.menubar import run
        run(a.port)
    return 0


def _memory_command(rest: list[str]) -> int:
    """`ctwin memory [clear]` — inspect or clear the local, private memory."""
    from . import memory
    if rest and rest[0] == "clear":
        print("cleared local memory." if memory.clear() else "nothing to clear.")
    else:
        print(memory.status())
    return 0


def _persona_command(rest: list[str]) -> int:
    """`ctwin persona [setup|clear]` — create/inspect the twin's persona."""
    from . import persona
    if rest and rest[0] == "setup":
        persona.setup()
    elif rest and rest[0] == "clear":
        print("cleared persona." if persona.clear() else "nothing to clear.")
    else:
        print(persona.status())
        p = persona.load()
        if not p.is_empty():
            print("\n--- how the twin sees you ---")
            print(persona.to_prompt())
    return 0


def _voiceprofile_command(rest: list[str]) -> int:
    """`ctwin voiceprofile add "Name" <file>` / `status` / `clear` — teach Anita
    to speak like someone, from samples of how they wrote."""
    from . import voice_profile as vp
    if rest and rest[0] == "add" and len(rest) >= 2:
        person = rest[1]
        text = ""
        if len(rest) >= 3 and Path(rest[2]).is_file():
            text = Path(rest[2]).read_text(encoding="utf-8")
        else:
            print(f"Paste {person}'s messages, then Ctrl-D:")
            text = sys.stdin.read()
        n = vp.add_samples(text, person=person)
        print(f"Learned {n} samples of {person}'s voice.")
    elif rest and rest[0] == "clear":
        print("cleared." if vp.clear_voice() else "nothing to clear.")
    else:
        print(vp.status())
    return 0


def _rhythms_command(rest: list[str]) -> int:
    """`ctwin rhythms` — show what Anita has learned about your day; or
    `ctwin rhythms set <key> <value>` to state one (e.g. sleep 23:00)."""
    from . import rhythms
    if len(rest) >= 3 and rest[0] == "set":
        rhythms.set_override(rest[1], " ".join(rest[2:]))
        print(f"noted: {rest[1]} = {' '.join(rest[2:])}")
    else:
        print(rhythms.status())
        print()
        print(rhythms.summary_for_prompt())
    return 0


def _remember_command(rest: list[str]) -> int:
    """`ctwin remember "fact"` — teach Anita something to keep."""
    from . import voice_profile as vp
    if rest:
        n = vp.remember(" ".join(rest))
        print(f"Got it. ({n} things remembered)")
    else:
        facts = vp.custom_facts()
        print("\n".join(f"- {f}" for f in facts) if facts else "nothing remembered yet.")
    return 0


def _control_command(rest: list[str]) -> int:
    """`ctwin control [on|status]` — show or hint at screen-control state."""
    from . import control
    if rest and rest[0] == "on":
        print("Enable screen control for a session by setting CTWIN_CONTROL=1, e.g.:")
        print("  CTWIN_CONTROL=1 python -m cognitive_twin \"what app am I in?\"")
    else:
        print(control.status())
    return 0


def _twin_command(rest: list[str]) -> int:
    """`ctwin twin [list|new <name>|use <name>|rm <name>]` — manage multiple twins.

    Each twin has its own persona, voice, and memory. The active twin is what
    every other command operates on.
    """
    from . import twins
    if rest and rest[0] == "new" and len(rest) > 1:
        name = " ".join(rest[1:])
        s = twins.create(name)
        print(f"created twin '{s}' and made it active.")
        print("  next: `ctwin persona setup`  then give it a voice with voice_clone.")
    elif rest and rest[0] == "use" and len(rest) > 1:
        name = " ".join(rest[1:])
        if twins.exists(name):
            twins.set_active(name)
            print(f"active twin → {twins.slug(name)}")
        else:
            print(f"no twin named '{name}'. Have: {', '.join(twins.list_twins()) or 'none'}")
            return 1
    elif rest and rest[0] == "rm" and len(rest) > 1:
        name = " ".join(rest[1:])
        print("removed." if twins.remove(name) else "no such twin.")
    elif rest and rest[0] in {"private", "unprivate"} and len(rest) > 1:
        name = " ".join(rest[1:])
        priv = rest[0] == "private"
        if twins.set_private(name, priv):
            print(f"{twins.slug(name)} is now {'private (cannot be exported)' if priv else 'shareable'}.")
        else:
            print(f"no twin named '{name}'.")
            return 1
    elif rest and rest[0] == "export" and len(rest) > 2:
        from . import twin_package
        name, out = rest[1], rest[2]
        res = twin_package.export_twin(name, out)
        if res.get("ok"):
            v = "with voice" if res["has_voice"] else "persona only"
            print(f"exported '{res['display_name']}' ({v}) → {res['path']}")
        else:
            print(f"export failed: {res.get('error')}")
            return 1
    elif rest and rest[0] == "import" and len(rest) > 1:
        from . import twin_package
        pkg = rest[1]
        name = " ".join(rest[2:]) if len(rest) > 2 else None
        res = twin_package.import_twin(pkg, name=name)
        if res.get("ok"):
            v = "with voice" if res["has_voice"] else "persona only"
            print(f"imported as twin '{res['twin']}' ({v}); it's now active.")
        else:
            print(f"import failed: {res.get('error')}")
            return 1
    else:
        print(twins.status())
    return 0


def _media_command(rest: list[str]) -> int:
    """`ctwin media [status|on camera|on mic|off]` — camera/mic consent.

    Off by default. `on` persists consent for a device; `off` revokes both.
    Per-session use without persisting: CTWIN_CAMERA=1 / CTWIN_MIC=1.
    """
    from . import media
    if rest and rest[0] == "on" and len(rest) > 1 and rest[1] in {"camera", "mic"}:
        c = media.grant(camera=True) if rest[1] == "camera" else media.grant(mic=True)
        print(f"allowed {rest[1]}. {media.status()}")
        print(f"(consent: camera={c['camera']}, mic={c['mic']})")
    elif rest and rest[0] == "off":
        media.revoke()
        print("revoked camera + mic. " + media.status())
    elif rest and rest[0] == "on":
        print("usage: ctwin media on camera   |   ctwin media on mic")
    else:
        print(media.status())
    return 0


def _ask_yn(action: str) -> bool:
    """Interactive y/N confirmation prompt (shared by control + media)."""
    try:
        ans = input(f"⚠ {action} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans in {"y", "yes"}


def _install_confirm() -> None:
    """Wire the confirmation hooks (screen control + camera/mic) to an
    interactive y/N prompt so every sensitive action asks the user first."""
    from . import control, media

    control.set_confirm(_ask_yn)
    media.set_confirm(_ask_yn)


def main(argv: list[str] | None = None) -> int:
    # subcommands handled before the main parser
    raw = list(sys.argv[1:] if argv is None else argv)

    # Point persona/memory/voice/media at the ACTIVE twin's folder before any
    # of them load. No-op (legacy flat layout) until the user makes a twin.
    # `twin` subcommands run against the registry itself, so don't activate for
    # them. Respect an explicit CTWIN_MEMORY_DIR (tests/power users) — only
    # activate when the caller hasn't pinned a dir.
    if not (raw and raw[0] == "twin") and "CTWIN_MEMORY_DIR" not in os.environ:
        from . import twins
        twins.activate()

    if raw and raw[0] == "setup":
        from . import onboarding
        return onboarding.run()
    if raw and raw[0] == "twin":
        return _twin_command(raw[1:])
    if raw and raw[0] == "voice":
        return _voice_command(raw[1:])
    if raw and raw[0] == "memory":
        return _memory_command(raw[1:])
    if raw and raw[0] == "control":
        return _control_command(raw[1:])
    if raw and raw[0] == "media":
        return _media_command(raw[1:])
    if raw and raw[0] == "persona":
        return _persona_command(raw[1:])
    if raw and raw[0] == "voiceprofile":
        return _voiceprofile_command(raw[1:])
    if raw and raw[0] == "remember":
        return _remember_command(raw[1:])
    if raw and raw[0] == "rhythms":
        return _rhythms_command(raw[1:])
    if raw and raw[0] == "reflect":
        return _reflect_command(raw[1:])
    if raw and raw[0] == "viz":
        return _viz_command(raw[1:])

    ap = argparse.ArgumentParser(prog="ctwin", description="Local-first personal AI agent.")
    ap.add_argument("prompt", nargs="*", help="one-shot prompt; omit for an interactive REPL")
    ap.add_argument("--model", help="Ollama model — pins this model and disables routing")
    ap.add_argument("--skills", action="store_true", help="list available skills and exit")
    ap.add_argument("--no-route", action="store_true", help="disable policy routing; use one model")
    ap.add_argument(
        "--route-explain", action="store_true",
        help="print which model/rule the policy picked for each request",
    )
    args = ap.parse_args(argv)

    if args.skills:
        # don't need Ollama just to list skills
        for n in default_registry.names():
            sk = default_registry.get(n)
            print(f"  {n:<14} {sk.description if sk else ''}")
        return 0

    # Fresh install + interactive (no prompt, real terminal): offer the guided
    # setup before we need Ollama, so a newcomer makes their twin first. Skipped
    # for one-shot prompts, pipes, and once onboarding has run.
    if not args.prompt and sys.stdin.isatty() and sys.stdout.isatty():
        from . import onboarding
        if onboarding.is_fresh_install():
            onboarding.offer()

    # An explicit --model pins one model (routing off); otherwise route by policy.
    use_routing = not args.no_route and not args.model
    agent = build_agent(args.model, route=use_routing)
    explain = args.route_explain

    # preflight: clear message if the brain isn't reachable. With routing on, the
    # model is chosen per request, so only require the server to be up here; a
    # routed model that isn't pulled is handled per-run with a graceful fallback.
    client = agent.client  # type: ignore[assignment]
    try:
        if use_routing:
            if not client.is_up():  # type: ignore[attr-defined]
                raise OllamaError("Ollama isn't running. Start it with `ollama serve`, then try again.")
        else:
            client.ensure_ready()  # type: ignore[attr-defined]
    except LLM_ERRORS as e:
        print(f"⚠ {e}", file=sys.stderr)
        return 1

    if args.prompt:
        return 0 if _run_once(agent, " ".join(args.prompt), explain) else 1

    # Interactive REPL — a friendly, guided chat session.
    _repl_banner()
    while True:
        try:
            line = input(f"{_repl_prompt()} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  take care 🌅")
            return 0
        if not line:
            continue
        if line in {"exit", "quit", "/exit", "/quit"}:
            print("  take care 🌅")
            return 0
        if line.startswith("/"):
            _repl_command(line)
            continue
        _run_once(agent, line, explain, repl=True)


def _active_twin_name() -> str:
    """The active twin's display name (persona name if set, else the slug)."""
    try:
        from . import persona, twins
        p = persona.load()
        if p.name:
            return p.name
        a = twins.active()
        return a or "your twin"
    except Exception:
        return "your twin"


def _repl_prompt() -> str:
    return f"{_active_twin_name()} »"


def _proactive_opening() -> list[str]:
    """What the twin says *first*, unprompted — the thing a static assistant
    never does. Composed entirely from local context: a time-aware greeting in
    the twin's voice, any thoughts it saved while you were away, and a gentle
    nudge about today if there's anything pending. Each piece is best-effort and
    silently skipped when unavailable, so this never errors or stalls startup."""
    who = _active_twin_name()
    lines: list[str] = []

    # 1) a warm, time-aware hello by name
    try:
        from . import rhythms
        part = rhythms.part_of_day()  # "morning"/"afternoon"/"evening"/"night"
    except Exception:
        part = "day"
    hello = {
        "morning": f"Good morning. {who} here.",
        "afternoon": f"Good afternoon — {who} here.",
        "evening": f"Good evening. It's {who}.",
        "night": f"Up late? {who}'s here.",
        "late night": f"It's late — {who}'s still here if you need me.",
    }.get(part, f"Hi, {who} here.")
    lines.append(hello)

    # 2) thoughts she had "while you were away" (proactive memory)
    try:
        from . import soul
        pending = soul.pending_reflections(clear=True)
        if pending:
            lines.append(f"I was thinking — {pending[0]['thought']}")
    except Exception:
        pass

    # 3) a light nudge about today, if a tasks file exists (no model call)
    try:
        from . import skills  # noqa: F401  (ensures builtins registered)
        from .skills.base import default_registry as _R
        import os as _os
        ws = Path(_os.environ.get("CTWIN_WORKSPACE", Path.home() / ".cognitive-twin" / "workspace"))
        if (ws / "tasks.md").is_file():
            lines.append("You've got a tasks list — want me to look at your day? (try: \"summarize my day\")")
    except Exception:
        pass

    return lines


def _repl_banner() -> None:
    who = _active_twin_name()
    # The twin reaches out first — proactive, not a static prompt.
    for ln in _proactive_opening():
        print(f"  {ln}")
    print(f"\n  (talking to {who} · type a message, /help for commands, /exit to leave)\n")


_REPL_HELP = """  commands:
    /help            show this
    /who             who you're talking to (the active twin)
    /twins           list your twins (* = active)
    /use <name>      switch to another twin
    /persona         show the active twin's persona
    /voice           voice-clone status for this twin
    /setup           guided setup for a new twin
    /exit            leave
  anything else is sent to your twin as a message."""


def _repl_command(line: str) -> None:
    """Handle an in-session /command so the user never has to leave the chat."""
    parts = line[1:].split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""
    from . import persona, twins, voice_clone

    if cmd in {"help", "?", "h"}:
        print(_REPL_HELP)
    elif cmd == "who":
        print(f"  {persona.status()}")
    elif cmd in {"twins", "list"}:
        print("  " + twins.status())
    elif cmd == "use":
        if not arg:
            print("  usage: /use <twin name>")
        elif twins.exists(arg):
            twins.activate(arg)
            print(f"  now talking to {_active_twin_name()}.")
        else:
            print(f"  no twin named '{arg}'. /twins to see them.")
    elif cmd == "persona":
        print("  " + persona.status())
        block = persona.to_prompt()
        if block:
            print("\n" + "\n".join("  " + ln for ln in block.splitlines()[:6]))
    elif cmd == "voice":
        print("  " + voice_clone.status())
    elif cmd == "setup":
        from . import onboarding
        onboarding.run()
    else:
        print(f"  unknown command '/{cmd}'. /help for the list.")


if __name__ == "__main__":
    raise SystemExit(main())
