"""
Visualize Engine — *see how the twin thinks*, from real on-device data.

Most assistants are a black box. This serves one local page (127.0.0.1, never
exposed off the machine): **the Mind** — the twin's brain as a living particle
nebula with its real knowledge constellated around it. Design references, per
the owner: a central fluid particle "mind" whose motion is a real D2Q9
lattice-Boltzmann simulation — FluidX3D's method (github.com/ProjectPhysX/
FluidX3D), ported by hand to plain JS, with its iron colorscale for velocity —
labeled memory nodes radiating constellation-style with a terminal HUD (the
Kronos brain look), and bbycroft.net/llm's idea that you should be able to
WATCH a prompt flow through the architecture. Dependency-free 2D canvas — no
build step, works offline.

  - perceives — the central nebula is her memory mass: thousands of particles
    tinted by the real mix of memory types, swirling with differential rotation
    around a dark core. Every REAL memory is a labeled node around the cloud,
    wired to it and to its related memories (landscape data). Hover to read.
  - how it works — the faculties (memory, persona, soul, mood, rhythms, shadow,
    router, voice…) are labeled stations on an inner ring, joined by the app's
    real wiring, with motes flowing along the conduits.
  - thinks — type a prompt and watch the actual thought: a particle stream
    enters the cloud, the memories recall() REALLY surfaces flash and pour in,
    the faculties on the real path light in order, and the router shows the
    model the policy actually picks. Nothing is faked; no memories = bare sky.

All data comes from the same on-device modules the agent uses (memory, soul,
mood, rhythms, brain, router) — nothing is fabricated, nothing leaves the machine.

Run:  python -m cognitive_twin viz        (opens the browser)
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HOST = "127.0.0.1"
DEFAULT_PORT = 7879  # voice UI uses 7878; sit next to it


# ---- gather real state -------------------------------------------------------
def _state() -> dict[str, Any]:
    """The twin's real inner state, assembled from the on-device modules."""
    out: dict[str, Any] = {}

    # who: active twin + persona
    try:
        from . import persona, twins
        out["twin"] = twins.active() or "default"
        p = persona.load()
        out["persona"] = {"name": p.name, "traits": p.traits, "likes": p.likes,
                          "values": p.values}
    except Exception:
        out["twin"] = None
        out["persona"] = {}

    # knowledge: recurring topics from local memory
    try:
        from . import memory
        pats = memory.patterns()
        out["topics"] = pats.get("topics", [])
        out["memory_count"] = pats.get("count", 0)
    except Exception:
        out["topics"] = []
        out["memory_count"] = 0

    # reflections the twin saved while away
    try:
        from . import soul
        out["reflections"] = [r.get("thought", "") for r in soul.pending_reflections(clear=False)]
        out["soul_status"] = soul.status() if hasattr(soul, "status") else ""
    except Exception:
        out["reflections"] = []
        out["soul_status"] = ""

    # mood + rhythm
    try:
        from . import rhythms
        out["part_of_day"] = rhythms.part_of_day()
    except Exception:
        out["part_of_day"] = ""
    try:
        from . import mood
        out["mood_reflective"] = mood.is_reflective() if hasattr(mood, "is_reflective") else None
    except Exception:
        out["mood_reflective"] = None

    return out


def _route(query: str) -> dict[str, Any]:
    """Run the real router on a query to show which model/rule would handle it."""
    try:
        from .agent.router import Router
        r = Router()
        d = r.route(query)
        return {"model": d.model, "rule": d.rule_id,
                "complexity": d.task_complexity, "risk": d.risk_level}
    except Exception as e:
        return {"error": str(e)}


def _landscape() -> dict[str, Any]:
    """The typed memory landscape (points laid out by relatedness, coloured by
    kind) — the data behind the constellation. Local only."""
    try:
        from . import brain
        return brain.landscape()
    except Exception as e:
        return {"points": [], "error": str(e)}


def _brain() -> dict[str, Any]:
    """Faculties + wiring + live state — the app's real anatomy."""
    try:
        from . import brain
        return brain.snapshot()
    except Exception as e:
        return {"nodes": [], "edges": [], "state": {}, "error": str(e)}


def _thought(q: str) -> dict[str, Any]:
    """Everything a real thought would touch, for the flow animation:
    the memories recall() actually surfaces for this prompt, the faculty path,
    and the model the policy really routes to. Honest — no invented steps."""
    out: dict[str, Any] = {"q": q}
    try:
        from . import memory
        hits = memory.recall(q, k=3)
        out["recall"] = [
            {"prompt": (e.get("prompt") or "").strip(),
             # trimmed exactly like brain.landscape() labels, so the client can
             # match a recalled memory to its node
             "label": ((p := (e.get("prompt") or "").strip())[:40] + "…")
                      if len((e.get("prompt") or "").strip()) > 41 else (e.get("prompt") or "").strip(),
             "ts": (e.get("ts") or "")[:10]}
            for e in hits
        ]
    except Exception:
        out["recall"] = []
    try:
        from . import brain
        out["path"] = brain.thought_path(q).get("path", [])
    except Exception:
        out["path"] = []
    out["route"] = _route(q)
    return out


# ---- page (self-contained: HTML+CSS+JS in one string) ------------------------
def _git(args: list[str]) -> str:
    """Ask the repo itself — the changelog and version are real history, not
    prose that drifts. Empty string if git isn't there; the pages degrade."""
    try:
        import subprocess
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        r = subprocess.run(["git", *args], cwd=root, capture_output=True,
                           text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _page() -> bytes:
    ver = _git(["rev-parse", "--short", "HEAD"]) or "dev"
    return _PAGE.replace("__VER__", ver).encode("utf-8")


def _about_page() -> bytes:
    """/about — what's built, the real changelog (git history), how a change
    ships, and the map of the whole thing. Server-rendered, zero JS."""
    import html as H
    ver = _git(["rev-parse", "--short", "HEAD"]) or "dev"
    n_commits = _git(["rev-list", "--count", "HEAD"]) or "?"
    raw = _git(["log", "--pretty=%ad%x09%s", "--date=format:%Y-%m-%d"])
    # group consecutive commits under their day, newest first — as it happened
    log_html, last_day = [], None
    for line in raw.splitlines():
        day, _, subject = line.partition("\t")
        if not subject:
            continue
        if day != last_day:
            log_html.append(f'<div class="day">{H.escape(day)}</div>')
            last_day = day
        log_html.append(f'<div class="entry">{H.escape(subject)}</div>')
    changelog = "\n".join(log_html) or '<div class="entry">no history readable here — the repo speaks when git can</div>'
    return _ABOUT.replace("__VER__", ver).replace("__COUNT__", n_commits) \
                 .replace("__LOG__", changelog).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def log_message(self, *a: Any) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.split("?")[0] in ("/", "/index.html"):
            self._send(200, _page(), "text/html; charset=utf-8")
        elif self.path.split("?")[0] == "/about":
            self._send(200, _about_page(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(200, _state())
        elif self.path.startswith("/api/route"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._json(200, _route(q or "what should I work on today?"))
        elif self.path == "/api/landscape":
            self._json(200, _landscape())
        elif self.path == "/api/brain":
            self._json(200, _brain())
        elif self.path.startswith("/api/thought"):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            self._json(200, _thought(q or "what should I focus on today?"))
        else:
            self._json(404, {"error": "not found"})


def make_server(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), _Handler)


def serve(port: int = DEFAULT_PORT, *, open_browser: bool = True) -> None:
    httpd = make_server(port)
    url = f"http://{HOST}:{port}"
    print(f"  Visualize Engine → {url}  (Ctrl-C to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
        httpd.shutdown()


# The Mind page — dependency-free HTML+canvas in one string (no build step,
# works offline). All data from the local APIs above.
_PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vera · The Mind</title>
<style>
  :root{ --mono: ui-monospace, "SF Mono", Menlo, monospace; }
  html,body{margin:0;height:100%;overflow:hidden;background:#04050a;color:#dfe4ee;
    font-family:var(--mono);-webkit-font-smoothing:antialiased}
  /* a canvas does NOT stretch with inset:0 (replaced element keeps its
     intrinsic size) — on a 2× display the backing store is twice the window
     and the centred heart lands in the bottom-right corner. Pin the box. */
  canvas{position:fixed;inset:0;display:block;width:100%;height:100%;
    opacity:0;transition:opacity .9s ease}
  .hud{position:fixed;pointer-events:none;z-index:2}
  .box{background:rgba(7,9,16,.78);border:1px solid rgba(170,190,230,.22);
    backdrop-filter:blur(6px);padding:6px 10px;font-size:10.5px;letter-spacing:.08em}
  #topbar{top:14px;left:50%;transform:translateX(-50%);display:flex;gap:8px;align-items:center}
  #topbar .live{color:#7fd1b9}
  #topbar .box{text-transform:uppercase}
  #who{top:14px;left:18px}
  #who .name{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:#eef2fa}
  #who .sub{color:#77809466;color:rgba(150,160,180,.75);font-size:10px;margin-top:3px;letter-spacing:.06em}
  #legend{bottom:42px;left:18px;display:flex;flex-direction:column;gap:6px;font-size:10px}
  #legend .chip{display:inline-flex;align-items:center;gap:7px;background:rgba(7,9,16,.7);
    border:1px solid rgba(170,190,230,.16);padding:3px 8px;letter-spacing:.08em;text-transform:uppercase}
  #legend .dot{width:7px;height:7px;border-radius:50%}
  #askbar{bottom:44px;left:50%;transform:translateX(-50%);pointer-events:auto;display:flex;gap:0}
  #askbar input{width:380px;background:rgba(7,9,16,.85);border:1px solid rgba(170,190,230,.28);
    color:#dfe4ee;padding:10px 14px;font-size:12px;outline:none;font-family:var(--mono)}
  #askbar input:focus{border-color:rgba(126,200,255,.65)}
  #askbar button{background:rgba(126,200,255,.16);border:1px solid rgba(126,200,255,.5);
    color:#bfe3ff;padding:10px 16px;font-size:11px;cursor:pointer;letter-spacing:.12em;
    text-transform:uppercase;font-family:var(--mono)}
  #askbar button:hover{background:rgba(126,200,255,.3)}
  #hint{bottom:90px;left:50%;transform:translateX(-50%);color:rgba(150,160,180,.55);font-size:10px;letter-spacing:.06em;white-space:nowrap}
  /* the thought chain — numbered stations joined by links that fill as it moves */
  #stages .stgh{font-size:9px;letter-spacing:.14em;text-transform:uppercase;
    color:rgba(150,160,180,.7);margin-bottom:9px}
  #stages .stg{display:flex;align-items:center;gap:9px;opacity:.26;transition:opacity .3s}
  #stages .stg.now{opacity:1}
  #stages .stg.done{opacity:.6}
  #stages .n{width:18px;height:18px;border-radius:50%;border:1px solid rgba(170,190,230,.5);
    display:inline-flex;align-items:center;justify-content:center;font-size:9px;flex:none;
    background:rgba(7,9,16,.8)}
  #stages .stg.now .n{border-color:#7ec8ff;color:#bfe3ff;box-shadow:0 0 10px rgba(126,200,255,.55)}
  #stages .stg.done .n{border-color:rgba(127,209,185,.7);color:#7fd1b9}
  #stages .stgline{width:1px;height:13px;background:rgba(170,190,230,.22);margin-left:9px}
  #stages .stgline.full{background:rgba(127,209,185,.55)}
  #card{display:none;background:rgba(7,9,16,.92);border:1px solid rgba(170,190,230,.3);
    padding:9px 12px;font-size:11.5px;max-width:300px;box-shadow:0 6px 24px rgba(0,0,0,.5)}
  #card .t{font-weight:600;margin-bottom:3px;letter-spacing:.1em;text-transform:uppercase;font-size:10px}
  #card .m{color:#8f96a6;font-size:10.5px;margin-top:3px}
  #answer{display:none;top:56px;right:18px;background:rgba(7,9,16,.92);border:1px solid rgba(126,200,255,.4);
    padding:12px 14px;font-size:11.5px;max-width:300px}
  #answer .t{font-weight:600;color:#7ec8ff;margin-bottom:6px;letter-spacing:.12em;text-transform:uppercase;font-size:10px}
  #answer .row{color:#aeb4c0;margin-top:3px}
  #answer .kv{color:#7fd1b9}
  #axes{bottom:42px;right:18px;color:rgba(190,200,220,.75);font-size:9.5px;text-transform:uppercase}
  /* the footer — a quiet instrument strip; every page ends the same way */
  #footer{position:fixed;left:0;right:0;bottom:0;height:26px;z-index:3;
    display:flex;align-items:center;gap:16px;padding:0 16px;
    background:rgba(5,7,13,.9);border-top:1px solid rgba(170,190,230,.14);
    backdrop-filter:blur(6px);font-size:9.5px;letter-spacing:.1em;
    text-transform:uppercase;color:rgba(150,160,180,.6);pointer-events:auto}
  #footer a{color:rgba(175,190,220,.78);text-decoration:none}
  #footer a:hover{color:#bfe3ff}
  #footer .sp{flex:1}
  #footer .ver{color:rgba(150,160,180,.42)}
</style></head><body>
<canvas id="sky"></canvas>
<div class="hud" id="who"><div class="name box" id="whoname">THE MIND</div><div class="sub" id="stats">reading her real state…</div></div>
<div class="hud" id="topbar"><span class="box"><span class="live">●</span> LIVE <span id="clock"></span></span></div>
<div class="hud" id="legend"></div>
<div class="hud" id="hint">drag to orbit her mind · scroll to zoom · double-click resets · hover any node</div>
<div class="hud box" id="axes">ANGLE · what &nbsp;&nbsp;RADIUS · strength &nbsp;&nbsp;HEIGHT · when</div>
<div class="hud" id="state" style="top:auto;bottom:122px;left:50%;transform:translateX(-50%);
  font-size:15px;letter-spacing:.04em;color:#dfe4ee;text-align:center;text-shadow:0 2px 12px rgba(0,0,0,.8)"></div>
<div class="hud" id="stages" style="top:50%;left:26px;transform:translateY(-50%);
  font-size:11px;color:rgba(200,210,230,.9);display:none"></div>
<div class="hud" id="askbar"><input id="q" placeholder="ask her something — watch the thought move…"><button id="go">think</button></div>
<div class="hud" id="card"></div>
<div class="hud" id="answer"></div>
<div id="footer">
  <span>VERA · A MIND ON THIS MACHINE</span>
  <span class="sp"></span>
  <a href="/">the mind</a>
  <a href="/about">what's built · changelog</a>
  <a href="/about#ship">how it ships</a>
  <a href="/about#map">site map</a>
  <span class="sp"></span>
  <span class="ver">build __VER__ · 127.0.0.1 only</span>
</div>
<div class="hud" id="modebtn" style="bottom:42px;right:18px;pointer-events:auto">
  <button id="mode" style="background:rgba(7,9,16,.7);border:1px solid rgba(170,190,230,.25);
    color:rgba(200,210,230,.8);padding:6px 12px;font:10px ui-monospace,Menlo,monospace;
    letter-spacing:.1em;cursor:pointer;text-transform:uppercase">details</button>
</div>
<script>
"use strict";
/* The Mind — her brain as a living particle nebula + the real knowledge
   constellated around it, with visible thought-flow. Design refs from the
   owner: a central fluid particle mind moved by a real lattice-Boltzmann
   simulation (FluidX3D's method, ported — see "the churn" below), labeled
   memory nodes in a terminal HUD (the Kronos brain look), and bbycroft's
   LLM viz idea — you should WATCH a prompt flow through the architecture.

   Honesty rules: every LABELED thing is real local state — memory nodes are
   real memories, station chips are the app's real faculties, the wiring is
   brain.py's real wiring, the thought path/recall/route come from the real
   modules. The nebula is her memory mass: its size and colour mix follow the
   real count and type mix. No memories = a bare, quiet mind. */

const cv = document.getElementById("sky"), ctx = cv.getContext("2d");
let W = 0, H = 0, DPR = 1;
// offscreen pair for the bloom pipeline: grains render to CLOUD_CV, then get
// blitted twice — sharp, and downscaled→upscaled through BLOOM_CV, which the
// browser's smoothing turns into a soft gaussian-ish glow. No filters needed.
const CLOUD_CV = document.createElement("canvas"), cctx = CLOUD_CV.getContext("2d");
const BLOOM_CV = document.createElement("canvas"), bctx = BLOOM_CV.getContext("2d");

/* ---------- live data ------------------------------------------------------ */
let STATE = {}, LAND = {points:[],links:[],types:{}}, BRAIN = {nodes:[],edges:[],state:{}};
let nodes = [];                       // real memories — labeled constellation
let chips = [];                       // the faculties — labeled stations
let glow = {};                        // id → highlight intensity (decays)
let streams = [];                     // flowing particles (thought + bursts)
let ripples = [];

/* ---------- view mode: simple (the graph anyone reads) vs details ------------ */
let MODE = localStorage.getItem("mindMode") || "simple";
// ?mode= wins (the app pins its Brain window to the human view)
{ const m = new URLSearchParams(location.search).get("mode");
  if (m === "simple" || m === "expert"){ MODE = m; localStorage.setItem("mindMode", m); } }
document.getElementById("mode").textContent = MODE === "simple" ? "details" : "simple view";
document.getElementById("mode").onclick = () => {
  MODE = MODE === "simple" ? "expert" : "simple";
  localStorage.setItem("mindMode", MODE);
  document.getElementById("mode").textContent = MODE === "simple" ? "details" : "simple view";
  hudRefresh();
};

/* ---------- deterministic jitter (stable across repolls) -------------------- */
function rnd(i){ let t = (i + 1) * 0x6D2B79F5;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }

/* ---------- camera: orbit the mind ------------------------------------------- */
/* The memory space is genuinely 3-D (see docs/memory-ia.md): drag orbits it
   (yaw + a clamped pitch), scroll zooms. The camera has hands now: a released
   drag keeps gliding (a throw), zoom eases instead of snapping, and clicking a
   memory VISITS it — the camera keeps it centred while you orbit around it.
   Double-click glides home. No free pan; travel is always TO something. */
const cam = { zoom: 1, tzoom: 1, yaw: 0, pitch: 0.42, cx: 0, cy: 0,
              vyaw: 0, vpitch: 0, drag: null };
const HOME = { yaw: 0, pitch: 0.42, zoom: 1 };
let follow = null;    // idx of the memory the camera keeps centred (click to visit)
let fly = null;       // eased camera flight {t,dur,from,to} — the intro + going home
function flyTo(to, dur){
  fly = { t: 0, dur, to,
          from: { yaw: cam.yaw, pitch: cam.pitch, zoom: cam.zoom, cx: cam.cx, cy: cam.cy } };
  cam.tzoom = to.zoom; cam.vyaw = cam.vpitch = 0;
}
// ?yaw=&pitch= — start from a given orbit angle (demos + screenshots);
// otherwise the first sight is an approach: from far out and high above,
// the mind grows from a distant glow to fill the frame
const qs = new URLSearchParams(location.search);
let introPending = false;
if (qs.get("yaw") || qs.get("pitch")){
  cam.yaw   = parseFloat(qs.get("yaw"))   || 0;
  cam.pitch = parseFloat(qs.get("pitch")) || 0.42;
} else {
  introPending = true;   // the flight runs only once the view proves itself
  cam.zoom = cam.tzoom = 0.22; cam.yaw = -2.1; cam.pitch = 0.98;
}
function S(x, y){ return { X: W/2 + (x - cam.cx)*cam.zoom, Y: H/2 + (y - cam.cy)*cam.zoom }; }
function toWorld(sx, sy){ return { x: (sx - W/2)/cam.zoom + cam.cx, y: (sy - H/2)/cam.zoom + cam.cy }; }
/* the entrance animation shows ONLY if it will work properly: data answered
   and the canvas box truly matches the window (a mis-sized view once put the
   heart in a corner — never animate a broken picture, just show it settled) */
function viewSane(){
  const r = cv.getBoundingClientRect();
  return W > 0 && H > 0 && Math.abs(r.width - W) < 2 && Math.abs(r.height - H) < 2;
}
let revealed = false;
function reveal(){
  if (revealed) return;
  revealed = true;
  if (introPending && viewSane()){
    flyTo({ yaw: HOME.yaw, pitch: HOME.pitch, zoom: 1, cx: 0, cy: 0 }, 3.2);
    setTimeout(startTour, 3500);      // land, then name the layers
  } else if (introPending){   // view can't vouch for itself: settle instantly
    cam.yaw = HOME.yaw; cam.pitch = HOME.pitch; cam.zoom = cam.tzoom = 1;
    setTimeout(startTour, 800);
  }
  introPending = false;
  cv.style.opacity = 1;
}
function R0(){ return Math.min(W, H); }
/* world 3-D (x: right, z: toward viewer at yaw 0, h: up) → flat world 2-D */
function project(x0, h, z0){
  const c = Math.cos(cam.yaw), s = Math.sin(cam.yaw);
  const x = x0*c - z0*s, z = x0*s + z0*c;
  return { x, y: z * cam.pitch - h * 0.9, z };   // z>0 = near, z<0 = far
}

function hexRgb(h){ if (!h || h[0] !== "#") return [160,180,255];
  const v = parseInt(h.slice(1), 16); return [(v>>16)&255, (v>>8)&255, v&255]; }

/* ---------- the nebula — her memory mass (perceives) ------------------------- */
/* A cloud of particles with differential rotation (inner turns faster, like a
   fluid vortex), a dark core, gentle vertical flattening, and a colour mix that
   follows the REAL memory-type mix. Rendered additively with tiny rects (fast). */
let cloud = [];
// neutral sparkle palette — white, warm gold, ice blue, soft magenta, violet
const NEUTRAL = [[236,240,250],[255,222,170],[170,200,255],[240,150,220],[190,150,255]];
function buildCloud(){
  const count = Math.min(6500, 1400 + (STATE.memory_count || 0) * 260 + ((LAND.points||[]).length ? 2200 : 0));
  // colour pool weighted by the real type mix (plus neutral sparkle)
  const pool = [];
  const types = LAND.types || {};
  Object.keys(types).forEach(t => {
    const m = types[t]; if (!m || !m.count) return;
    const c = hexRgb(m.color);
    for (let k = 0; k < m.count; k++) pool.push(c);
  });
  if (!pool.length) pool.push([120,135,170]);   // no memories: dim, quiet blue
  cloud = Array.from({length: count}, (_, i) => {
    const band = rnd(i*11);
    // dense inner band + long soft tail; hole in the very middle (dark core)
    const r = 0.13 + (band < 0.72 ? Math.pow(rnd(i*11+1), 1.4) * 0.5
                                  : 0.36 + Math.pow(rnd(i*11+1), 0.8) * 0.85);
    const neutral = rnd(i*11+2) < 0.34;
    let c = neutral ? NEUTRAL[(rnd(i*11+3)*NEUTRAL.length)|0] : pool[(rnd(i*11+3)*pool.length)|0];
    // astro colour grade: warm toward the heart, cool toward the rim
    const gfrac = Math.max(0, Math.min(1, (r - 0.13) / 1.1));
    const wm = (1 - gfrac) * 0.42, cm = gfrac * 0.30;
    c = [ c[0]*(1-wm) + 255*wm, c[1]*(1-wm) + 212*wm, c[2]*(1-wm) + 158*wm ];
    c = [ (c[0]*(1-cm) + 140*cm)|0, (c[1]*(1-cm) + 180*cm)|0, (c[2]*(1-cm) + 255*cm)|0 ];
    const tier = rnd(i*11+7);
    const a0 = rnd(i*11+4) * 6.2832;
    return {
      u: Math.cos(a0) * r, v: Math.sin(a0) * r,        // in-plane position (disc units)
      hr: r,                                           // home radius — the shape holds
      y: (rnd(i*11+5) - 0.5) * (0.72 + r*0.5),         // a full, rounded mass
      c, s: tier < 0.72 ? 1.2 : (tier < 0.95 ? 2 : 3),
      spark: tier >= 0.985,                            // a few luminous grains
      tw: rnd(i*11+8) * 6.2832,
      al: 0.40 + rnd(i*11+9) * 0.55
    };
  });
}
/* ---------- the churn — a real lattice-Boltzmann fluid (FluidX3D, ported) ----- */
/* The owner's motion reference is FluidX3D (github.com/ProjectPhysX/FluidX3D),
   a lattice-Boltzmann solver. So the mass is driven by that repo's actual
   method, scaled to a mind: a D2Q9 lattice (same velocity set and weights —
   4/9, 1/9, 1/36 — BGK collide + stream, half-way bounce-back walls,
   velocity-shift forcing) stepped at a fixed 60 Hz in the disc plane. The
   grains advect through the REAL simulated field and take FluidX3D's own iron
   colorscale as they speed up. Slow stir-rods orbit inside the disc (its
   moving-boundary demos) and the lattice does what fluids genuinely do —
   sheds, folds, and carries vortices. Thinking stirs harder. */
const FN = 96, FQ = 9;                        // grid side + D2Q9
const F_EXT = 1.35;                           // grid spans [-F_EXT, F_EXT]² disc units
const F_TAU = 0.56;                           // BGK relaxation → viscosity
const F_CX = [0,1,-1,0,0,1,-1,1,-1], F_CY = [0,0,0,1,-1,1,-1,-1,1];
const F_W  = [4/9,1/9,1/9,1/9,1/9,1/36,1/36,1/36,1/36];
const F_OPP = [0,2,1,4,3,6,5,8,7];
const CELL = (2*F_EXT)/FN, G2C = 1/CELL, LATV = CELL*60;  // lattice u ↔ disc-units/s
let ffA = new Float32Array(FN*FN*FQ), ffB = new Float32Array(FN*FN*FQ);
const fux = new Float32Array(FN*FN), fuy = new Float32Array(FN*FN),
      fcw = new Float32Array(FN*FN);          // velocity + curl (vorticity)
const fbx = new Float32Array(FN*FN), fby = new Float32Array(FN*FN);  // base swirl
let rods = [], fAcc = 0;
function buildFluid(){
  rods = Array.from({length: 4}, (_, i) => ({
    r: 0.24 + rnd(i*29) * 0.5, a: rnd(i*29+1) * 6.2832,
    w: (rnd(i*29+2) < 0.5 ? -1 : 1) * (0.25 + rnd(i*29+3) * 0.3),
    g: 0.020 + rnd(i*29+4) * 0.016 }));
  for (let y = 0; y < FN; y++) for (let x = 0; x < FN; x++){
    const n = y*FN + x;
    const px = (x + 0.5)*CELL - F_EXT, py = (y + 0.5)*CELL - F_EXT;
    const r = Math.hypot(px, py) || 0.001;
    const w0 = (0.16 / (0.25 + r)) / LATV;    // the same differential rotation, lattice units
    const fade = Math.max(0, 1 - Math.pow(r/F_EXT, 4));  // still near the walls
    fbx[n] = -py * w0 * fade; fby[n] = px * w0 * fade;
    const ux = fbx[n], uy = fby[n], uu = 1.5*(ux*ux + uy*uy);
    for (let q = 0; q < FQ; q++){
      const cu = 3*(F_CX[q]*ux + F_CY[q]*uy);
      ffA[n*FQ + q] = F_W[q] * (1 + cu + 0.5*cu*cu - uu);
    }
  }
}
buildFluid();
function stepFluid(heat){
  rods.forEach(rd => { rd.a += rd.w * (1 + heat) / 60; });
  const R = rods.map(rd => ({ x: Math.cos(rd.a)*rd.r, y: Math.sin(rd.a)*rd.r,
                              g: rd.g * (1 + heat*2.2) }));
  const K = 0.06, iT = 1/F_TAU, bs = 1 + heat*0.8;
  for (let y = 0; y < FN; y++) for (let x = 0; x < FN; x++){
    const n = y*FN + x, b = n*FQ;
    let rho = 0, ux = 0, uy = 0;
    for (let q = 0; q < FQ; q++){ const v = ffA[b+q]; rho += v; ux += v*F_CX[q]; uy += v*F_CY[q]; }
    ux /= rho; uy /= rho;
    // velocity-shift forcing: relax toward the base swirl + the rods' stir
    const px = (x + 0.5)*CELL - F_EXT, py = (y + 0.5)*CELL - F_EXT;
    let tx = fbx[n]*bs, ty = fby[n]*bs;
    for (let j = 0; j < R.length; j++){
      const dx = px - R[j].x, dy = py - R[j].y;
      const k = R[j].g / ((dx*dx + dy*dy + 0.012) * LATV);
      tx -= dy*k; ty += dx*k;
    }
    ux += (tx - ux)*K; uy += (ty - uy)*K;
    const sp = Math.hypot(ux, uy);            // Mach guard — LBM wants u ≪ c
    if (sp > 0.16){ ux *= 0.16/sp; uy *= 0.16/sp; }
    fux[n] = ux; fuy[n] = uy;
    // BGK collide + push-stream, bounce-back at the walls
    const uu = 1.5*(ux*ux + uy*uy);
    for (let q = 0; q < FQ; q++){
      const cu = 3*(F_CX[q]*ux + F_CY[q]*uy);
      const feq = F_W[q]*rho*(1 + cu + 0.5*cu*cu - uu);
      const out = ffA[b+q] + (feq - ffA[b+q])*iT;
      const nx = x + F_CX[q], ny = y + F_CY[q];
      if (nx < 0 || nx >= FN || ny < 0 || ny >= FN) ffB[b + F_OPP[q]] = out;
      else ffB[(ny*FN + nx)*FQ + q] = out;
    }
  }
  const sw = ffA; ffA = ffB; ffB = sw;
  // vorticity — FluidX3D paints the fluid's curl; we tint grains with it
  for (let y = 1; y < FN-1; y++) for (let x = 1; x < FN-1; x++){
    const n = y*FN + x;
    fcw[n] = 0.5*((fuy[n+1] - fuy[n-1]) - (fux[n+FN] - fux[n-FN]));
  }
}
function fieldAt(u, v){   // bilinear sample → [disc-units/s x, y, |curl|]
  const gx = Math.max(0, Math.min(FN - 1.001, (u + F_EXT)*G2C - 0.5));
  const gy = Math.max(0, Math.min(FN - 1.001, (v + F_EXT)*G2C - 0.5));
  const x0 = gx|0, y0 = gy|0, fx = gx - x0, fy = gy - y0;
  const n00 = y0*FN + x0, n10 = n00 + 1, n01 = n00 + FN, n11 = n01 + 1;
  const ux = (fux[n00]*(1-fx) + fux[n10]*fx)*(1-fy) + (fux[n01]*(1-fx) + fux[n11]*fx)*fy;
  const uy = (fuy[n00]*(1-fx) + fuy[n10]*fx)*(1-fy) + (fuy[n01]*(1-fx) + fuy[n11]*fx)*fy;
  return [ux*LATV, uy*LATV, Math.abs(fcw[n00])];
}
/* FluidX3D's own colorscale_iron (kernel.cpp), ported: 0 → black … 1 → white heat */
function ironColor(x){
  x = Math.max(0, Math.min(4, 4 * (1 - x)));
  let r = 1, g = 0, b = 0;
  if (x < 0.66666667){ g = 1; b = 1 - x*1.5; }
  else if (x < 2){ g = 1.5 - x*0.75; }
  else if (x < 3){ r = 2 - x*0.5; b = x - 2; }
  else { r = 2 - x*0.5; b = 4 - x; }
  return [r*255, g*255, b*255];
}
function cloudR(){ return R0() * 0.225; }
function drawCloud(now, dt, scale){
  const Rc = cloudR() * (scale || 1);
  cctx.clearRect(0, 0, W, H);
  cctx.globalCompositeOperation = "lighter";
  const heat = Math.min(1, streams.length / 120);      // thinking = the mind stirs
  // a heartbeat: every ~8s a soft shimmer washes outward through the mass
  const beatT = (now % 8000) / 8000;
  const waveR = 0.13 + beatT * 1.4;
  const beatGain = Math.sin(beatT * Math.PI) * 0.5;
  // the lattice runs at a fixed 60 Hz whatever the display refreshes at
  fAcc = Math.min(fAcc + dt, 3/60);
  while (fAcc >= 1/60){ stepFluid(heat); fAcc -= 1/60; }
  for (let i = 0; i < cloud.length; i++){
    const p = cloud[i];
    const r = Math.hypot(p.u, p.v) || 0.001;
    // ride the simulated fluid, plus a weak spring back to the home radius so
    // the mass churns without dissolving
    const f = fieldAt(p.u, p.v);
    const err = (p.hr - r) / r;
    const du = f[0] + p.u * err * 0.5;
    const dv = f[1] + p.v * err * 0.5;
    p.u += du * dt; p.v += dv * dt;
    const wob = 1 + 0.05 * Math.sin(now * 0.0006 + p.tw);
    const w = project(p.u * Rc * wob, p.y * Rc * 0.55, p.v * Rc * wob);
    const P = S(w.x, w.y);
    // the streak: project a step along the velocity too — grains in fast flow
    // draw as short threads of light (the FluidX3D signature), slow ones as points
    const w2 = project((p.u + du * 0.22) * Rc * wob, p.y * Rc * 0.55,
                       (p.v + dv * 0.22) * Rc * wob);
    const P2 = S(w2.x, w2.y);
    const run = Math.hypot(P2.X - P.X, P2.Y - P.Y);
    const front = w.z >= 0;
    const twk = 0.75 + 0.25 * Math.sin(now * 0.0016 + p.tw);
    const pulse = Math.max(0, 1 - Math.abs(r - waveR) * 5) * beatGain;
    // velocity + curl colouring, FluidX3D's habit — but calibrated so the iron
    // scale ignites only ABOVE the bulk rotation (subtract the floor): the
    // nebula keeps her memory-type palette, and just the genuinely fast flow
    // and vortex edges burn gold. (Uncalibrated, everything saturated yellow.)
    const spd = Math.hypot(f[0], f[1]);
    const s = Math.min(1, Math.max(0, (spd - 0.13) * 5) + f[2] * 3.5);
    cctx.globalAlpha = Math.min(1, (p.al * twk + pulse * 0.55 + s * 0.2)) * (front ? 1 : 0.45);
    const IC = ironColor(0.45 + s * 0.5), wI = s * 0.5;
    cctx.fillStyle = "rgb(" + ((p.c[0]*(1-wI) + IC[0]*wI)|0) + ","
                            + ((p.c[1]*(1-wI) + IC[1]*wI)|0) + ","
                            + ((p.c[2]*(1-wI) + IC[2]*wI)|0) + ")";
    const sz = p.s * Math.max(0.7, Math.sqrt(cam.zoom));
    if (run > 1.6){
      cctx.strokeStyle = cctx.fillStyle;
      cctx.lineWidth = sz * 0.8;
      cctx.beginPath(); cctx.moveTo(P.X, P.Y); cctx.lineTo(P2.X, P2.Y); cctx.stroke();
    } else {
      cctx.fillRect(P.X - sz/2, P.Y - sz/2, sz, sz);
    }
    if (p.spark){                                     // luminous grains get a halo
      cctx.globalAlpha = 0.18 * twk;
      cctx.beginPath(); cctx.arc(P.X, P.Y, sz * 2.6, 0, 7); cctx.fill();
    }
  }
  // a soft luminous heart behind the dark core (the dense unresolved middle)
  const core = S(0, 0), CR = Rc * 0.34 * cam.zoom;
  let g = cctx.createRadialGradient(core.X, core.Y, 0, core.X, core.Y, CR * 2.1);
  g.addColorStop(0, "rgba(190,200,255,0.16)"); g.addColorStop(0.5, "rgba(230,180,240,0.07)");
  g.addColorStop(1, "rgba(190,200,255,0)");
  cctx.globalAlpha = 1;
  cctx.fillStyle = g; cctx.beginPath(); cctx.arc(core.X, core.Y, CR * 2.1, 0, 7); cctx.fill();
  // composite: once sharp, once through the bloom pipeline
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  ctx.drawImage(CLOUD_CV, 0, 0, W, H);
  bctx.clearRect(0, 0, BLOOM_CV.width, BLOOM_CV.height);
  bctx.drawImage(CLOUD_CV, 0, 0, BLOOM_CV.width, BLOOM_CV.height);
  ctx.globalAlpha = 0.6;
  ctx.drawImage(BLOOM_CV, 0, 0, W, H);
  ctx.globalAlpha = 1;
  ctx.restore();
  // the dark core — a quiet centre the mind turns around
  g = ctx.createRadialGradient(core.X, core.Y, 0, core.X, core.Y, CR);
  g.addColorStop(0, "rgba(3,4,9,0.97)"); g.addColorStop(0.72, "rgba(3,4,9,0.6)");
  g.addColorStop(1, "rgba(3,4,9,0)");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(core.X, core.Y, CR, 0, 7); ctx.fill();
  // a bright swirl ring, slowly precessing (the awake mind)
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  ctx.translate(core.X, core.Y);
  ctx.rotate(now * 0.00012);
  ctx.shadowColor = "rgba(190,215,255,0.9)"; ctx.shadowBlur = 10;
  ctx.strokeStyle = "rgba(210,228,255,0.75)"; ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.ellipse(0, 0, CR * 0.66, CR * 0.26, 0.5, 0.5, 3.7); ctx.stroke();
  ctx.shadowColor = "rgba(255,200,150,0.8)";
  ctx.strokeStyle = "rgba(255,214,170,0.55)"; ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.ellipse(0, 0, CR * 0.78, CR * 0.32, 0.5, 3.8, 6.5); ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.restore();
}

/* ---------- the simple view: her memory as a LIVING GRAPH -------------------- */
/* The Obsidian idea, made hers: every memory is a node, every real relation an
   edge (brain.landscape's links — nothing invented). A force layout lets the
   clusters emerge on their own. Life shows as events anyone reads:
     - node CREATION: she learns something → a spark is born from her heart
     - node CONNECTION: she remembers → the path lights from memory to heart
   Idle she breathes; working she stirs. Plain words underneath say which. */
let gnodes = [], gedges = [], gindex = {};
let lastMemCount = -1, statusLine = "", statusUntil = 0;
function setStatus(text, holdMs){
  statusLine = text;
  statusUntil = holdMs ? performance.now() + holdMs : 0;
}
function buildGraph(){
  const pts = LAND.points || [];
  const old = gindex; gindex = {};
  gedges = (LAND.links || []).slice();
  const deg = {};
  gedges.forEach(l => { deg[l.a] = (deg[l.a]||0) + 1; deg[l.b] = (deg[l.b]||0) + 1; });
  const born = lastMemCount >= 0 && pts.length > lastMemCount;
  gnodes = pts.map((p, i) => {
    const prev = old["n" + i];
    const seed = rnd(i * 31) * 6.2832, rr = R0() * (0.18 + rnd(i * 31 + 1) * 0.22);
    const isNew = born && i >= lastMemCount;
    const n = prev || {
      // newborns start at her heart and fly out — visibly LEARNED
      x: isNew ? 0 : Math.cos(seed) * rr,
      y: isNew ? 0 : Math.sin(seed) * rr * 0.8,
      z: isNew ? 0 : (rnd(i * 31 + 2) - 0.5) * rr * 1.4,
      vx: 0, vy: 0, vz: 0
    };
    n.idx = i; n.label = p.label; n.type = p.type; n.color = p.color;
    n.ts = p.ts; n.deg = deg[i] || 0; n.heat = p.heat || 0; n.hit = null;
    // freshness: memories from the last two days carry a visible warmth,
    // fading over a week — "what's new in her mind", readable at a glance
    const age = (Date.now() - Date.parse(p.ts || 0)) / 86400000;
    n.fresh = isFinite(age) ? Math.max(0, 1 - age / 7) : 0;
    gindex["n" + i] = n;
    return n;
  });
  if (born){
    setStatus("she just learned something new", 4000);
    ripples.push({ x: 0, y: 0, r: 8, a: 0.9 });
  }
  lastMemCount = pts.length;
}
function stepGraph(dt){
  // small-n force layout in TRUE 3D — the same space the heart lives in, so
  // orbit and zoom (your hand) are the depth cues. springs on real links,
  // a firm centre pull, and a hard spherical rim: always framed, always whole
  const N = gnodes.length;
  const REP = R0() * R0() * 0.0022, SPRING = 2.2, LEN = R0() * 0.13;
  const RIM = R0() * 0.40;
  for (let i = 0; i < N; i++){
    const a = gnodes[i];
    let fx = -a.x * 0.55, fy = -a.y * 0.55, fz = -a.z * 0.55; // toward her heart
    for (let j = 0; j < N; j++){
      if (i === j) continue;
      const b = gnodes[j];
      const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
      const d2 = dx*dx + dy*dy + dz*dz + 60;
      fx += dx / d2 * REP; fy += dy / d2 * REP; fz += dz / d2 * REP;
    }
    a.fx = fx; a.fy = fy; a.fz = fz;
  }
  gedges.forEach(l => {
    const a = gindex["n" + l.a], b = gindex["n" + l.b];
    if (!a || !b) return;
    const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    const d = Math.hypot(dx, dy, dz) || 1;
    const f = (d - LEN) * SPRING / d;
    a.fx += dx * f; a.fy += dy * f; a.fz += dz * f;
    b.fx -= dx * f; b.fy -= dy * f; b.fz -= dz * f;
  });
  // keep clear of the heart, and inside the rim (both spheres)
  const CORE = cloudR() * 0.62;
  gnodes.forEach(n => {
    const d = Math.hypot(n.x, n.y, n.z) || 1;
    if (d < CORE){
      n.fx += n.x / d * (CORE - d) * 8;
      n.fy += n.y / d * (CORE - d) * 8;
      n.fz += n.z / d * (CORE - d) * 8;
    }
    n.vx = (n.vx + n.fx * dt) * 0.86;
    n.vy = (n.vy + n.fy * dt) * 0.86;
    n.vz = (n.vz + n.fz * dt) * 0.86;
    n.x += n.vx * dt; n.y += n.vy * dt; n.z += n.vz * dt;
    const dd = Math.hypot(n.x, n.y, n.z);
    if (dd > RIM){ n.x *= RIM / dd; n.y *= RIM / dd; n.z *= RIM / dd; }
  });
}
/* hexagon path — the owner's choice for memory cells: honeycomb, not bubbles */
function hexPath(c, X, Y, r, rot){
  c.beginPath();
  for (let k = 0; k < 6; k++){
    const a = rot + k * Math.PI / 3;
    const x = X + Math.cos(a) * r, y = Y + Math.sin(a) * r;
    k ? c.lineTo(x, y) : c.moveTo(x, y);
  }
  c.closePath();
}

/* ---------- the anatomy, drawn — the design explains itself ------------------ */
/* Two dashed Kronos-style layer rings orbit with the camera: the inner one
   circles her consciousness (the churn), the outer circles memory (where the
   cells live). Each ring carries its name on the edge nearest the viewer, so
   the strata read like an anatomical plate — no manual needed. */
let coreShine = 0, nodeShine = 0, edgeShine = 0;   // tour highlights, decaying
function ring(r, label, alpha){
  ctx.beginPath();
  for (let k = 0; k <= 72; k++){
    const a = (k / 72) * 6.2832;
    const w = project(Math.cos(a) * r, 0, Math.sin(a) * r);
    const P = S(w.x, w.y);
    k ? ctx.lineTo(P.X, P.Y) : ctx.moveTo(P.X, P.Y);
  }
  ctx.strokeStyle = "rgba(170,190,235," + alpha + ")";
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 7]); ctx.stroke(); ctx.setLineDash([]);
  const a0 = Math.PI / 2 - cam.yaw;                // the point facing the viewer
  const w0 = project(Math.cos(a0) * r, 0, Math.sin(a0) * r);
  const P0 = S(w0.x, w0.y);
  ctx.font = "9px ui-monospace, Menlo, monospace"; ctx.textAlign = "center";
  ctx.fillStyle = "rgba(195,206,235," + Math.min(0.8, 0.3 + alpha * 4) + ")";
  ctx.fillText(label, P0.X, P0.Y + 14);
  ctx.textAlign = "left";
}
function drawAnatomy(){
  ring(cloudR() * 0.68, "CONSCIOUSNESS", 0.07 + coreShine * 0.45);
  ring(R0() * 0.43,     "MEMORY",        0.055 + nodeShine * 0.4);
}

/* the landing tour — once per tab, right after the approach: each layer lights
   as she names it in plain words. Everything highlighted is real state. */
let tour = null;
function startTour(){
  if (MODE !== "simple" || sessionStorage.getItem("mindTour")) return;
  sessionStorage.setItem("mindTour", "1");
  tour = { t: 0, fired: {} };
}
function stepTour(dt){
  if (!tour) return;
  tour.t += dt;
  [
    { at: 0.3,  k: "a", s: "this churn is her consciousness — always awake",
      go(){ coreShine = 1; ripples.push({ x: 0, y: 0, r: cloudR() * 0.4, a: 0.7 }); } },
    { at: 3.2,  k: "b", s: "each cell around it is a memory — its colour is its kind",
      go(){ nodeShine = 1; } },
    { at: 6.2,  k: "c", s: "the threads are how her memories relate",
      go(){ edgeShine = 1; } },
    { at: 9.2,  k: "d", s: "ask her something below — and watch the thought move",
      go(){} },
    { at: 13.0, k: "e", s: "", go(){ tour = null; } },
  ].forEach(st => {
    if (tour && tour.t >= st.at && !tour.fired[st.k]){
      tour.fired[st.k] = true;
      if (st.s) setStatus(st.s, 2700);
      st.go();
    }
  });
}

/* at rest her mind still murmurs: every few seconds a faint spark rides one
   REAL connection between two memories — pure ambience, drawn only on edges
   that exist (same licence as the motes on the faculty wiring) */
let synAt = 0;
function synapse(now){
  if (!gedges.length || now < synAt) return;
  synAt = now + 2400 + Math.random() * 2800;
  const l = gedges[(Math.random() * gedges.length) | 0];
  const a = gindex["n" + l.a], b = gindex["n" + l.b];
  if (!a || !b || a.px === undefined) return;
  spawnStream({ x: a.px, y: a.py }, { x: b.px, y: b.py },
    { n: 5, color: hexRgb(a.color), spread: 10, stagger: 0.3 });
}

let focusIdx = null;   // hovered memory (last frame): its neighbourhood lights
function drawGraph(now){
  let hover = null;
  // project every node through the SAME camera the heart uses (orbit with a
  // drag, zoom with a scroll, double-click resets — your hand is the depth cue)
  gnodes.forEach(n => {
    const w = project(n.x, -n.y, n.z);
    n.px = w.x; n.py = w.y; n.pz = w.z;
  });
  const maxZ = R0() * 0.40;
  const depthOf = n => 0.45 + 0.55 * ((n.pz / maxZ) + 1) / 2;   // far dim, near bright
  // the hovered memory's neighbourhood (Obsidian's best move): it and its
  // relations hold full light, everything else steps back
  const nbr = new Set();
  if (focusIdx !== null){
    nbr.add(focusIdx);
    gedges.forEach(l => {
      if (l.a === focusIdx) nbr.add(l.b);
      if (l.b === focusIdx) nbr.add(l.a);
    });
  }
  const dimmed = n => focusIdx !== null && !nbr.has(n.idx) ? 0.3 : 1;
  // edges — the connections ARE the point; recall and focus set them alight
  ctx.save();
  gedges.forEach(l => {
    const a = gindex["n" + l.a], b = gindex["n" + l.b];
    if (!a || !b) return;
    const A = S(a.px, a.py), B = S(b.px, b.py);
    const hot = (glow["node:" + l.a] || 0) + (glow["node:" + l.b] || 0);
    const focused = focusIdx !== null && (l.a === focusIdx || l.b === focusIdx);
    const dp = (depthOf(a) + depthOf(b)) / 2 * (focusIdx !== null && !focused ? 0.25 : 1);
    ctx.strokeStyle = "rgba(160,180,235," +
      Math.min(0.8, (0.10 + (l.w || 0) * 0.2 + hot * 0.5 + (focused ? 0.4 : 0) + edgeShine * 0.35) * dp) + ")";
    ctx.lineWidth = hot > 0.1 || focused ? 1.6 : 0.8;
    ctx.beginPath(); ctx.moveTo(A.X, A.Y); ctx.lineTo(B.X, B.Y); ctx.stroke();
  });
  // the tethers to her BRAIN: every memory is held to the heart, and the
  // thread's weight is honest — the strength of the memory (how often it's
  // been recalled into real thinking) plus its freshness. strong memories
  // hold on thick and bright; strays barely hang on.
  gnodes.forEach(n => {
    const P = S(n.px, n.py);
    const m = Math.hypot(n.px, n.py) || 1;
    const E = S(n.px / m * cloudR() * 0.5, n.py / m * cloudR() * 0.5);
    const hot = glow["node:" + n.idx] || 0;
    const grip = Math.min(1, n.heat * 0.8 + n.fresh * 0.4);
    const focused = focusIdx === n.idx;
    ctx.strokeStyle = "rgba(200,212,240," +
      ((0.05 + grip * 0.18 + hot * 0.5 + (focused ? 0.35 : 0)) * depthOf(n) * dimmed(n)) + ")";
    ctx.lineWidth = 0.5 + grip * 1.2 + (hot > 0.1 || focused ? 0.8 : 0);
    ctx.beginPath(); ctx.moveTo(E.X, E.Y); ctx.lineTo(P.X, P.Y); ctx.stroke();
  });
  ctx.restore();
  // nodes far-to-near: sized by connectedness (an Obsidian instinct), depth-lit,
  // warm when fresh, labels by level of detail
  const named = new Set(gnodes.slice().sort((a, b) => b.deg - a.deg).slice(0, 10));
  gnodes.slice().sort((a, b) => a.pz - b.pz).forEach(n => {
    const P = S(n.px, n.py);
    const dp = depthOf(n) * dimmed(n);
    const hot = glow["node:" + n.idx] || 0;
    const r = (3.0 + Math.min(4, n.deg * 0.7) + hot * 3 + nodeShine * 2.5) * depthOf(n);
    // memory CELLS: flat-top hexagons (each keeps its own slight tilt)
    const rot = rnd(n.idx * 13) * 0.5;
    ctx.globalAlpha = dp;
    ctx.fillStyle = n.color; ctx.shadowColor = n.color;
    ctx.shadowBlur = 8 + hot * 16 + n.fresh * 8 + nodeShine * 10;
    hexPath(ctx, P.X, P.Y, r, rot); ctx.fill(); ctx.shadowBlur = 0;
    if (n.fresh > 0.3){          // new this week: a warm ring, fading with age
      ctx.strokeStyle = "rgba(255,214,160," + (0.5 * n.fresh * dp) + ")";
      ctx.lineWidth = 1;
      hexPath(ctx, P.X, P.Y, r + 2.5, rot); ctx.stroke();
    }
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    hexPath(ctx, P.X, P.Y, Math.max(0.9, r * 0.34), rot); ctx.fill();
    const near = Math.hypot(P.X - mouse.x, P.Y - mouse.y) < r + 6;
    // come close and she shows you what's written: past ~1.7× zoom, everything
    // near the centre of your gaze is named (level of detail by travel)
    const gazed = cam.zoom > 1.7 && Math.hypot(P.X - W/2, P.Y - H/2) < R0() * 0.3;
    n.hit = ((named.has(n) && dp > 0.72) || near || gazed || hot > 0.1 || nbr.has(n.idx))
      ? pill(P, nodeShort(n), n.color, hot > 0.1 || focusIdx === n.idx, n.px < 0 ? -1 : 1)
      : null;
    ctx.globalAlpha = 1;
    if (near || inRect(n.hit, mouse.x, mouse.y)) hover = { n, P };
  });
  focusIdx = hover ? hover.n.idx : null;
  return hover;
}
/* docs/memory-ia.md: ANGLE = what it is (type sector, related pulled together),
   RADIUS = how strong (heat: the connected sit near her core, strays drift out),
   HEIGHT = when (new memories float above the plane, settling as they age). */
const SECTOR = { emotion:0, task:1, opinion:2, knowledge:3 };
let SECTOR_LAYOUT = {};   // type → {start, arc}; captions read this too
function buildNodes(){
  const pts = (LAND.points || []).slice();
  const maxHeat = Math.max(0.001, ...pts.map(p => p.heat || 0));
  const byAge = pts.slice().sort((a, b) => (a.ts||"").localeCompare(b.ts||""));
  // with a big log, only the most connected memories keep permanent labels —
  // the rest stay quiet dots until hovered, so the constellation never clutters
  const byHeat = pts.slice().sort((a, b) => (b.heat || 0) - (a.heat || 0));
  const labeled = new Set(byHeat.slice(0, 26));
  // group per sector; within it, order by landscape-x so related sit together
  const groups = {};
  pts.forEach(p => { (groups[p.type] = groups[p.type] || []).push(p); });
  Object.values(groups).forEach(g => g.sort((a, b) => (a.x || 0) - (b.x || 0)));
  // ANGLE arcs sized by how much of her lives in each type — fixed 90° sectors
  // stacked every label into one cramped column once one type dominated
  const present = Object.keys(SECTOR).filter(t => (groups[t] || []).length);
  const total = present.reduce((s, t) => s + groups[t].length, 0) || 1;
  SECTOR_LAYOUT = {};
  let sum = 0;
  present.forEach(t => {
    const a = Math.max(0.55, (groups[t].length / total) * Math.PI * 2);
    SECTOR_LAYOUT[t] = { arc: a };  sum += a;
  });
  let start = -Math.PI / 2;
  present.forEach(t => {
    SECTOR_LAYOUT[t].arc *= (Math.PI * 2) / sum;   // renormalize to a full turn
    SECTOR_LAYOUT[t].start = start;
    start += SECTOR_LAYOUT[t].arc;
  });
  nodes = pts.map(p => {
    const i = (LAND.points || []).indexOf(p);
    const g = groups[p.type], gi = g.indexOf(p);
    const lay = SECTOR_LAYOUT[p.type] || { start: -Math.PI/2, arc: Math.PI/2 };
    const margin = Math.min(0.21, lay.arc * 0.12);
    const a = lay.start + margin
            + ((gi + 0.5) / Math.max(1, g.length)) * (lay.arc - margin * 2);
    // RADIUS — strength: heat 1 → hugging the mass, heat 0 → far periphery;
    // neighbours alternate slightly in and out so their pills never stack
    const strength = (p.heat || 0) / maxHeat;
    const r = cloudR() * 1.3 + (R0() * 0.44 - cloudR() * 1.3) * (1 - strength)
            + (gi % 2 ? R0() * 0.035 : 0);
    // HEIGHT — age: newest floats highest, settling toward the plane
    const ageRank = byAge.indexOf(p) / Math.max(1, byAge.length - 1);  // 0 old → 1 new
    const h = R0() * (-0.04 + ageRank * 0.20);
    const n = { idx: i, a, r, h, x3: Math.cos(a)*r, z3: Math.sin(a)*r,
                type: p.type, color: p.color, label: p.label, ts: p.ts,
                heat: p.heat || 0, strength, named: labeled.has(p),
                px: 0, py: 0, pz: 0, hit: null };
    const w = project(n.x3, n.h, n.z3);
    n.px = w.x; n.py = w.y; n.pz = w.z;
    return n;
  });
}
function nodeShort(n){ return n.label.length > 26 ? n.label.slice(0, 25) + "…" : n.label; }

/* ---------- the faculties — labeled stations (how it works) ------------------ */
const P_COLOR = { memory:"#7fd1b9", persona:"#ffd9a0", soul:"#c98bff", mood:"#ff7eb6",
  rhythms:"#8fb7ff", activity:"#9adf7c", shadow:"#f3c969", router:"#7ec8ff", voice:"#ff9e3d" };
function buildChips(){
  const cores = (BRAIN.nodes || []).filter(n => n.kind === "core");
  const N = cores.length;
  chips = cores.map((n, i) => {
    const a = -Math.PI/2 + (i / Math.max(1, N)) * Math.PI * 2;
    const r = R0() * 0.258;
    return { id: n.id, label: n.label, role: n.role || "",
             a, x: Math.cos(a)*r, y: Math.sin(a)*r*0.86,
             color: P_COLOR[n.id] || "#9fb4ff", hit: null };
  });
}
function badge(id){
  const st = BRAIN.state || {};
  if (id === "memory")  return (st.memory_count || 0) + " memories";
  if (id === "shadow")  return (st.open_tasks || 0) + " open tasks";
  if (id === "rhythms") return st.part_of_day || "";
  if (id === "soul")    return (st.reflections || 0) + " thoughts waiting";
  return "";
}

/* ---------- flowing particles (FluidX3D feel) -------------------------------- */
/* A stream particle rides a quadratic bezier with a little perpendicular
   turbulence — dozens together read as fluid pouring between stations. */
function spawnStream(from, to, opts){
  const o = opts || {};
  const n = o.n || 40;
  for (let i = 0; i < n; i++){
    const mid = { x: (from.x + to.x)/2 + (Math.random()-0.5) * (o.spread || 60),
                  y: (from.y + to.y)/2 + (Math.random()-0.5) * (o.spread || 60) };
    streams.push({ p0: {x:from.x, y:from.y}, p1: mid, p2: {x:to.x, y:to.y},
                   t: -Math.random() * (o.stagger || 0.5),
                   v: 0.55 + Math.random() * 0.5,
                   c: o.color || [126,200,255],
                   s: Math.random() < 0.85 ? 1.4 : 2.2 });
  }
}
function stepStreams(dt){
  streams = streams.filter(p => p.t < 1);
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  streams.forEach(p => {
    p.t += dt * p.v;
    if (p.t < 0){ p.lX = undefined; return; }
    const t = p.t, u = 1 - t;
    const x = u*u*p.p0.x + 2*u*t*p.p1.x + t*t*p.p2.x;
    const y = u*u*p.p0.y + 2*u*t*p.p1.y + t*t*p.p2.y;
    const P = S(x, y);
    const fade = Math.sin(Math.min(1, Math.max(0, t)) * Math.PI);
    const col = p.c[0] + "," + p.c[1] + "," + p.c[2];
    if (p.lX !== undefined){       // a thread, not a dot — the fluid look
      ctx.strokeStyle = "rgba(" + col + "," + (0.5 * fade) + ")";
      ctx.lineWidth = p.s * 0.9;
      ctx.beginPath(); ctx.moveTo(p.lX, p.lY); ctx.lineTo(P.X, P.Y); ctx.stroke();
    }
    ctx.fillStyle = "rgba(" + col + "," + (0.85 * fade) + ")";
    ctx.fillRect(P.X - p.s/2, P.Y - p.s/2, p.s * cam.zoom, p.s * cam.zoom);
    p.lX = P.X; p.lY = P.Y;
  });
  ctx.restore();
}

/* ---------- the thought (thinks) --------------------------------------------- */
let thought = null;   // {t, recall:[node], path:[chipId], route, fired:{}}
async function think(q){
  const A = document.getElementById("answer"); A.style.display = "none";
  let d; try{ d = await j("/api/thought?q=" + encodeURIComponent(q)); }catch(_){ return; }
  const recall = [];
  (d.recall || []).forEach(r => {
    const n = nodes.find(n => n.label === r.label);
    if (n) recall.push(n);
  });
  const path = (d.path || []).filter(id => chips.find(c => c.id === id));
  // the plain-words stages (the isometric-pipeline idea, told in captions):
  // timed to the REAL events — recall flashes, then the answer forms
  const model = (d.route || {}).model;
  const stages = [
    { at: 0.0, label: "heard you" },
    { at: 0.55, label: recall.length
        ? "remembering — " + recall.length + (recall.length === 1 ? " memory surfaces" : " memories surface")
        : "nothing familiar — thinking fresh" },
    { at: 0.6 + recall.length * 0.35 + 0.3, label: "connecting what she knows" },
    { at: 0.6 + recall.length * 0.35 + 0.3 + path.length * 0.4,
      label: "choosing words" + (model ? " — " + model : "") },
  ];
  thought = { t: 0, recall, path, route: d.route || {}, fired: {}, stages };
  // the prompt enters: a stream from the ask bar up into the cloud
  const start = toWorld(W/2, H - 84);
  spawnStream(start, {x: 0, y: cloudR() * 0.4}, { n: 70, color: [126,200,255], spread: 90, stagger: 0.8 });
}
document.getElementById("go").onclick = () => { const q = document.getElementById("q").value.trim(); if (q) think(q); };
document.getElementById("q").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("go").click(); });

function stepThought(dt){
  if (!thought) return;
  thought.t += dt;
  const T = thought;
  // recalled memories flash + pour into her heart, one by one — real recall().
  // in the simple view the streams rise from the GRAPH nodes as wide soft
  // threads converging on the centre (the flow the owner chose)
  T.recall.forEach((n, i) => {
    const at = 0.6 + i * 0.35, key = "r" + i;
    if (T.t >= at && !T.fired[key]){
      T.fired[key] = true;
      glow["node:" + n.idx] = 1;
      const g = gindex["n" + n.idx];
      const sx = (MODE === "simple" && g) ? (g.px || 0) : n.px;
      const sy = (MODE === "simple" && g) ? (g.py || 0) : n.py;
      ripples.push({ x: sx, y: sy, r: 6, a: 0.8 });
      spawnStream({x: sx, y: sy}, {x: 0, y: 0},
        MODE === "simple"
          ? { n: 48, color: hexRgb(n.color), spread: 26, stagger: 0.55 }
          : { n: 30, color: hexRgb(n.color), spread: 40, stagger: 0.4 });
    }
  });
  // then the faculties light along the real path (details view only —
  // the simple view says the same thing in words, stage by stage)
  const base = 0.6 + T.recall.length * 0.35 + 0.3;
  if (MODE !== "simple") T.path.forEach((id, i) => {
    const at = base + i * 0.4, key = "p" + i;
    if (T.t >= at && !T.fired[key]){
      T.fired[key] = true;
      glow["chip:" + id] = 1;
      const c = chips.find(c => c.id === id);
      if (c){
        ripples.push({ x: c.x, y: c.y, r: 6, a: 0.7 });
        const prev = i > 0 ? chips.find(x => x.id === T.path[i-1]) : null;
        spawnStream(prev || {x:0, y:0}, c, { n: 26, color: hexRgb(c.color), spread: 50, stagger: 0.3 });
      }
    }
  });
  // the staged story, plain words lighting as each REAL step fires
  if (MODE === "simple" && T.stages){
    const el = document.getElementById("stages");
    el.style.display = "block";
    // the chain of events, drawn AS a chain: each real step lights the moment
    // it happens, and the link beneath it fills once the thought has passed
    const ai = T.stages.reduce((m, s, i) => T.t >= s.at ? i : m, -1);
    el.innerHTML = '<div class="stgh">the thought, step by step</div>'
      + T.stages.map((s, i) =>
        '<div class="stg ' + (i < ai ? "done" : i === ai ? "now" : "next") + '">'
        + '<span class="n">' + (i + 1) + '</span><span>' + s.label + '</span></div>'
        + (i < T.stages.length - 1
            ? '<div class="stgline' + (i < ai ? " full" : "") + '"></div>' : "")
      ).join("");
  }
  // arrival: the honest routing result
  const done = base + T.path.length * 0.4 + 0.5;
  if (T.t >= done && !T.fired.end){
    T.fired.end = true;
    if (MODE === "simple"){
      setStatus("answered — she drew on " + T.recall.length +
                (T.recall.length === 1 ? " memory" : " memories"), 6000);
      setTimeout(() => { document.getElementById("stages").style.display = "none"; }, 2500);
    }
    const A = document.getElementById("answer"), r = T.route || {};
    if (r.model){ A.innerHTML = '<div class="t">how she answers</div>'
      + '<div class="row">model <span class="kv">' + r.model + '</span></div>'
      + '<div class="row">rule <span class="kv">' + (r.rule || "—") + '</span></div>'
      + '<div class="row">complexity ' + (r.complexity || "—") + ' · risk ' + (r.risk || "—") + '</div>'
      + '<div class="row" style="margin-top:5px;color:#8f96a6">routed locally — nothing left this machine</div>';
      A.style.display = "block"; }
    thought = null;
  }
}

/* ---------- interaction ------------------------------------------------------ */
let mouse = { x: -1, y: -1 }, lastHover = null, dragMoved = 0;
const card = document.getElementById("card");
cv.addEventListener("mousemove", e => {
  mouse = { x: e.clientX, y: e.clientY };
  if (cam.drag){
    const dx = e.clientX - cam.drag.x, dy = e.clientY - cam.drag.y;
    cam.yaw   += dx * 0.006;
    cam.pitch  = Math.max(0.06, Math.min(1.05, cam.pitch + dy * 0.003));
    // remember the hand's speed — release becomes a throw that glides out
    cam.vyaw   = cam.vyaw   * 0.4 + dx * 0.006 * 60 * 0.6;
    cam.vpitch = cam.vpitch * 0.4 + dy * 0.003 * 60 * 0.6;
    cam.drag = { x: e.clientX, y: e.clientY, t: performance.now(),
                 moved: cam.drag.moved + Math.abs(dx) + Math.abs(dy) };
  }
});
cv.addEventListener("mousedown", e => { fly = null; cam.vyaw = cam.vpitch = 0;
  cam.drag = { x: e.clientX, y: e.clientY, t: performance.now(), moved: 0 };
  cv.style.cursor = "grabbing"; });
window.addEventListener("mouseup", () => {
  if (cam.drag){
    dragMoved = cam.drag.moved;
    // a throw only if the hand was still moving at release
    if (performance.now() - cam.drag.t > 120) cam.vyaw = cam.vpitch = 0;
  }
  cam.drag = null; cv.style.cursor = "grab"; });
cv.addEventListener("click", () => {
  // a click (not a drag) on a memory: VISIT it — the camera glides over and
  // keeps it centred; dragging now orbits around that memory, not the middle
  if (dragMoved > 6 || !lastHover) return;
  follow = lastHover.n.idx;
  fly = null;
  cam.tzoom = Math.max(cam.tzoom, 1.9);
});
cv.addEventListener("wheel", e => { e.preventDefault(); fly = null;
  const f = e.deltaY < 0 ? 1.12 : 1/1.12;
  cam.tzoom = Math.max(0.35, Math.min(4.5, cam.tzoom * f)); }, { passive:false });
cv.addEventListener("dblclick", () => { follow = null;
  flyTo({ yaw: HOME.yaw, pitch: HOME.pitch, zoom: 1, cx: 0, cy: 0 }, 1.1); });
cv.style.cursor = "grab";
/* the visited memory, resolved fresh each frame (rebuilds replace node objects) */
function followNode(){
  if (follow === null) return null;
  const n = MODE === "simple" ? gindex["n" + follow]
                              : nodes.find(n => n.idx === follow);
  return (n && n.px !== undefined) ? n : null;
}

/* ---------- HUD --------------------------------------------------------------- */
function hudRefresh(){
  const name = (STATE.persona && STATE.persona.name) || "your twin";
  document.getElementById("whoname").textContent = "THE MIND — " + name.toUpperCase();
  // the simple view speaks human: hide the instrument HUD, warm placeholder
  const simple = MODE === "simple";
  document.getElementById("axes").style.display = simple ? "none" : "block";
  // navigation must be discoverable in BOTH views — the simple one just says it human
  document.getElementById("hint").textContent = simple
    ? "drag to look around her mind · scroll to come closer · click a memory to visit it · double-click to step back"
    : "drag to orbit · throw to spin · scroll to zoom · click a memory to visit it · double-click resets";
  // the legend answers "what am I looking at" — both views deserve it
  document.getElementById("legend").style.display = "flex";
  document.getElementById("state").style.display = simple ? "block" : "none";
  if (!simple) document.getElementById("stages").style.display = "none";
  document.getElementById("q").placeholder = simple
    ? "ask her anything — watch her think…"
    : "ask her something — watch the thought move…";
  const st = BRAIN.state || {};
  const bits = [(STATE.memory_count || 0) + " memories"];
  if ((STATE.topics || []).length) bits.push("returns to: " + STATE.topics.slice(0,3).join(", "));
  if (st.open_tasks) bits.push(st.open_tasks + " open tasks");
  if (STATE.part_of_day) bits.push(STATE.part_of_day);
  document.getElementById("stats").textContent = bits.join(" · ");
  // the key to the whole picture — every element of the design, named
  const lg = document.getElementById("legend"); lg.innerHTML = "";
  const key = (txt, dot) => {
    const c = document.createElement("span"); c.className = "chip";
    c.innerHTML = (dot ? '<span class="dot" style="background:' + dot
                 + ';box-shadow:0 0 6px ' + dot + '"></span>' : "") + txt;
    lg.appendChild(c);
  };
  key("the churn — her consciousness", "#cfd8f2");
  Object.keys(LAND.types || {}).forEach(k => {
    const t = LAND.types[k]; if (!t || !t.count) return;
    key(t.label + " memories · " + t.count, t.color);
  });
  key("threads — memories that relate");
  key("moving light — a thought", "#7ec8ff");
}
function clockTick(){
  const d = new Date();
  const pad = n => String(n).padStart(2, "0");
  document.getElementById("clock").textContent =
    pad(d.getMonth()+1) + "/" + pad(d.getDate()) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
}
setInterval(clockTick, 5000); clockTick();

/* ---------- data load ---------------------------------------------------------- */
async function j(u){ return await (await fetch(u)).json(); }
let CLOUD_KEY = "";   // rebuild the fluid mass only when the data really changed —
                      // a poll must never snap advected grains back to their homes
async function loadAll(){
  try{ STATE = await j("/api/state"); }catch(_){}
  try{ LAND = await j("/api/landscape"); }catch(_){}
  try{ BRAIN = await j("/api/brain"); }catch(_){}
  const key = (STATE.memory_count || 0) + "|" +
    Object.entries(LAND.types || {}).map(([k, t]) => k + ":" + (t.count || 0)).join(",");
  if (key !== CLOUD_KEY){ CLOUD_KEY = key; buildCloud(); }
  buildNodes(); buildChips(); buildGraph(); hudRefresh();
}
function resize(){
  DPR = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  cv.width = W * DPR; cv.height = H * DPR;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  // grains render at native resolution — on retina every 1px thread resolves
  CLOUD_CV.width = W * DPR; CLOUD_CV.height = H * DPR;
  cctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  BLOOM_CV.width = Math.ceil(W/5); BLOOM_CV.height = Math.ceil(H/5);
  buildNodes(); buildChips();
}
window.addEventListener("resize", resize);
resize();
setInterval(loadAll, 12000);
loadAll().then(() => {
  reveal();
  // ?demo=1 — auto-run one visible thought (handy for demos + screenshots)
  if (location.search.indexOf("demo") >= 0)
    setTimeout(() => think("how is mom doing today"), 1200);
});
setTimeout(reveal, 2500);   // never leave the mind dark, even if an API stalls

/* ---------- ambience ----------------------------------------------------------- */
const BG_PAL = [[200,215,255],[236,240,250],[255,225,190]];
const bgStars = Array.from({length: 260}, (_, i) => ({
  x: rnd(i*13)*1.9-0.95, y: rnd(i*13+1)*1.9-0.95, z: 0.2+rnd(i*13+2)*0.8,
  s: 0.35 + Math.pow(rnd(i*13+3), 2)*1.2, tw: rnd(i*13+4)*6.2832,
  c: BG_PAL[(rnd(i*13+5)*3)|0] }));

/* ---------- label pill (canvas) ------------------------------------------------- */
function pill(P, text, color, hot, side, edged){
  ctx.font = "10px ui-monospace, Menlo, monospace";
  // snapped to whole pixels: a 1px border on a fractional coordinate blurs
  const w = Math.ceil(ctx.measureText(text).width + (edged ? 16 : 12)), h = 16;
  const x = Math.round(side < 0 ? P.X - 10 - w : P.X + 10);
  const y = Math.round(P.Y - h/2);
  ctx.fillStyle = hot ? "rgba(14,20,34,0.95)" : "rgba(7,9,16,0.82)";
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = hot ? color : "rgba(170,190,230,0.22)";
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
  if (edged){                       // faculties carry their colour as an edge bar
    ctx.fillStyle = color;
    ctx.fillRect(side < 0 ? x + w - 3 : x, y, 3, h);
  }
  ctx.fillStyle = hot ? "#eef2fa" : "rgba(210,218,232,0.85)";
  ctx.fillText(text, x + (edged && side >= 0 ? 9 : 6), y + 11.5);
  return { x, y, w, h };
}
function inRect(r, mx, my){ return r && mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h; }

/* ---------- render loop ---------------------------------------------------------- */
let last = performance.now(), hoverHold = false;
function frame(now){
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  // self-healing frame: if the viewport changed and the resize event was
  // missed (webview quirks), notice and re-measure — the heart stays centred
  if (window.innerWidth !== W || window.innerHeight !== H) resize();
  // she is never frozen — but in the simple view the CAMERA is: a graph that
  // drifts forever reads as "why is it circling", not as alive. life comes
  // from the heart and the threads, not from spinning the room.
  if (MODE !== "simple" && !cam.drag && !hoverHold && !fly) cam.yaw += dt * 0.012;
  // camera dynamics: a flight in progress, else the throw + eased zoom + follow
  if (fly){
    fly.t += dt;
    // a stuttering flight is worse than none — sustained slow frames end it clean
    if (dt > 0.09 && (fly.slow = (fly.slow || 0) + 1) > 5) fly.t = fly.dur;
    const u = Math.min(1, fly.t / fly.dur);
    const e = u < 0.5 ? 4*u*u*u : 1 - Math.pow(-2*u + 2, 3)/2;   // ease in-out
    cam.yaw   = fly.from.yaw   + (fly.to.yaw   - fly.from.yaw)   * e;
    cam.pitch = fly.from.pitch + (fly.to.pitch - fly.from.pitch) * e;
    cam.zoom  = fly.from.zoom  + (fly.to.zoom  - fly.from.zoom)  * e;
    cam.cx    = fly.from.cx    + (fly.to.cx    - fly.from.cx)    * e;
    cam.cy    = fly.from.cy    + (fly.to.cy    - fly.from.cy)    * e;
    if (u >= 1) fly = null;
  } else {
    if (!cam.drag){          // the throw: a released orbit glides, then settles
      cam.yaw  += cam.vyaw * dt;
      cam.pitch = Math.max(0.06, Math.min(1.05, cam.pitch + cam.vpitch * dt));
      const k = Math.pow(0.08, dt); cam.vyaw *= k; cam.vpitch *= k;
    }
    cam.zoom += (cam.tzoom - cam.zoom) * Math.min(1, dt * 7);
    const F = followNode();  // glide toward the visited memory (or back home)
    cam.cx += ((F ? F.px : 0) - cam.cx) * Math.min(1, dt * 4);
    cam.cy += ((F ? F.py : 0) - cam.cy) * Math.min(1, dt * 4);
  }
  stepThought(dt);
  Object.keys(glow).forEach(k => { glow[k] *= Math.pow(0.4, dt); if (glow[k] < 0.02) delete glow[k]; });
  ctx.clearRect(0, 0, W, H);

  // deep-space vignette + two faint colour washes for depth. The washes know
  // what time it is where the owner sits (rhythms.part_of_day): dawn gold in
  // the morning, clear blue by day, ember violet at evening, deep at night.
  const bg = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, Math.max(W,H)*0.7);
  bg.addColorStop(0, "#080b16"); bg.addColorStop(1, "#03040a");
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  const DAYWASH = {
    morning:   ["234,170,80,0.06",  "120,140,220,0.045"],
    afternoon: ["70,140,220,0.055", "40,150,140,0.05"],
    evening:   ["200,110,70,0.055", "110,70,190,0.055"],
    night:     ["98,70,180,0.055",  "40,130,150,0.05"],
  };
  DAYWASH["late night"] = DAYWASH.night;
  const wcol = DAYWASH[STATE.part_of_day] || DAYWASH.night;
  let wash = ctx.createRadialGradient(W*0.2, H*0.15, 0, W*0.2, H*0.15, W*0.55);
  wash.addColorStop(0, "rgba(" + wcol[0] + ")"); wash.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = wash; ctx.fillRect(0, 0, W, H);
  wash = ctx.createRadialGradient(W*0.85, H*0.85, 0, W*0.85, H*0.85, W*0.5);
  wash.addColorStop(0, "rgba(" + wcol[1] + ")"); wash.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = wash; ctx.fillRect(0, 0, W, H);

  // faint stars
  bgStars.forEach(d => {
    // stars answer the camera — yaw sweeps them, travel slides them (parallax)
    const px = W/2 + d.x*W*0.75 + (cam.yaw*36 - cam.cx*0.22)*d.z;
    const py = H/2 + d.y*H*0.75 - cam.cy*0.22*d.z;
    ctx.globalAlpha = (0.12 + 0.3*d.z) * (0.8 + 0.2*Math.sin(now*0.0012 + d.tw));
    ctx.fillStyle = "rgb(" + d.c[0] + "," + d.c[1] + "," + d.c[2] + ")";
    ctx.beginPath(); ctx.arc(px, py, d.s, 0, 7); ctx.fill();
  });
  ctx.globalAlpha = 1;

  // her mind — the living cloud (in the simple view it is the HEART the
  // memory graph converges on, half-size, with the graph carrying the story)
  let hoverNode = null, hoverChip = null;
  if (MODE === "simple"){
    drawCloud(now, dt, 0.5);
    drawAnatomy();
    stepGraph(dt);
    const h = drawGraph(now);
    if (h) hoverNode = h;
    synapse(now);
    stepTour(dt);
    const dk = Math.pow(0.5, dt);          // tour highlights breathe back out
    coreShine *= dk; nodeShine *= dk; edgeShine *= dk;
    if (thought && !fly){                  // the moving light, named while it moves
      const cp = S(0, 0), cr = cloudR() * 0.5 * cam.zoom;
      ctx.font = "9px ui-monospace, Menlo, monospace"; ctx.textAlign = "center";
      ctx.globalAlpha = 0.6; ctx.fillStyle = "#7ec8ff";
      ctx.fillText("A THOUGHT, MOVING", cp.X, cp.Y - cr - 12);
      ctx.globalAlpha = 1; ctx.textAlign = "left";
    }
    // plain words for the state — working vs resting, no jargon
    const st = document.getElementById("state");
    const idle = "resting — " + gnodes.length + " memories, "
               + gedges.length + " connections"
               + (STATE.part_of_day ? " · " + STATE.part_of_day : "");
    st.textContent = (statusUntil && now < statusUntil) ? statusLine
                   : (thought ? "thinking…" : idle);
  } else {
  drawCloud(now, dt);

  // wiring between faculties (the real flow diagram), motes drifting along
  (BRAIN.edges || []).forEach((e, i) => {
    if (e.kind !== "wired") return;
    const a = chips.find(c => c.id === e.source), b = chips.find(c => c.id === e.target);
    if (!a || !b) return;
    const A = S(a.x, a.y), Bp = S(b.x, b.y);
    // arc the conduit outward so it skirts the cloud instead of crossing it
    const mx = (a.x + b.x)/2, my = (a.y + b.y)/2;
    const mm = Math.hypot(mx, my) || 1;
    const k = R0() * 0.30 / mm;
    const C = S(mx * Math.max(1, k), my * Math.max(1, k));
    const hot = (glow["chip:" + e.source] || 0) + (glow["chip:" + e.target] || 0);
    ctx.strokeStyle = "rgba(140,160,220," + (0.06 + Math.min(0.3, hot * 0.3)) + ")";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(A.X, A.Y); ctx.quadraticCurveTo(C.X, C.Y, Bp.X, Bp.Y); ctx.stroke();
    const ph = ((now * 0.00016) + i * 0.17) % 1, u = 1 - ph;
    const qx = u*u*A.X + 2*u*ph*C.X + ph*ph*Bp.X, qy = u*u*A.Y + 2*u*ph*C.Y + ph*ph*Bp.Y;
    ctx.fillStyle = "rgba(170,195,255,0.5)";
    ctx.fillRect(qx - 1, qy - 1, 2, 2);
  });

  // sector captions — the WHAT axis, whispered at the rim
  Object.keys(SECTOR).forEach(t => {
    const meta = (LAND.types || {})[t]; if (!meta || !meta.count) return;
    const lay = SECTOR_LAYOUT[t]; if (!lay) return;
    const mid = lay.start + lay.arc / 2;
    const RR = R0() * 0.47;
    const w = project(Math.cos(mid)*RR, -R0()*0.015, Math.sin(mid)*RR);
    const P = S(w.x, w.y);
    ctx.globalAlpha = 0.16 + 0.14 * ((w.z / RR) + 1) / 2;
    ctx.fillStyle = meta.color; ctx.font = "9px ui-monospace, Menlo, monospace";
    ctx.textAlign = "center";
    ctx.fillText(meta.label.toUpperCase(), P.X, P.Y);
    ctx.globalAlpha = 1; ctx.textAlign = "left";
  });

  // memory constellation on its 3 axes — project, then draw far-to-near
  nodes.forEach(n => {
    const w = project(n.x3, n.h, n.z3);
    n.px = w.x; n.py = w.y; n.pz = w.z;
  });
  (LAND.links || []).forEach(l => {
    const a = nodes.find(n => n.idx === l.a), b = nodes.find(n => n.idx === l.b);
    if (!a || !b) return;
    const A = S(a.px, a.py), Bp = S(b.px, b.py);
    ctx.strokeStyle = "rgba(150,170,255," + (0.05 + (l.w || 0) * 0.18) + ")";
    ctx.lineWidth = 0.7; ctx.beginPath(); ctx.moveTo(A.X, A.Y); ctx.lineTo(Bp.X, Bp.Y); ctx.stroke();
  });
  const maxZ = R0() * 0.44;
  nodes.slice().sort((a, b) => a.pz - b.pz).forEach(n => {
    const P = S(n.px, n.py);
    const depth = 0.62 + 0.38 * ((n.pz / maxZ) + 1) / 2;   // far = dimmer, smaller
    const hot = glow["node:" + n.idx] || 0;
    const near = Math.hypot(P.X-mouse.x, P.Y-mouse.y) < 10;
    // tether to the cloud edge, with a tick where it meets the mass
    const m = Math.hypot(n.px, n.py) || 1;
    const E = S(n.px/m * cloudR() * 1.02, n.py/m * cloudR() * 1.02);
    ctx.strokeStyle = "rgba(190,205,235," + ((0.15 + hot * 0.5) * depth) + ")";
    ctx.lineWidth = hot > 0.1 ? 1.2 : 0.7;
    ctx.beginPath(); ctx.moveTo(P.X, P.Y); ctx.lineTo(E.X, E.Y); ctx.stroke();
    ctx.fillStyle = "rgba(190,205,235,0.4)";
    ctx.fillRect(E.X - 1, E.Y - 1, 2, 2);
    // the node dot — sized by strength (the RADIUS axis, restated in the dot)
    const r = (2.2 + n.strength * 2.2 + hot * 2) * depth;
    ctx.globalAlpha = depth;
    ctx.fillStyle = n.color; ctx.shadowColor = n.color; ctx.shadowBlur = 6 + hot * 14;
    ctx.beginPath(); ctx.arc(P.X, P.Y, r, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
    // a crisp white heart in every dot — reads as a point of light, not a blob
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.beginPath(); ctx.arc(P.X, P.Y, Math.max(0.6, r * 0.34), 0, 7); ctx.fill();
    // the label pill (screen-side aware so text points away from the centre);
    // unnamed nodes stay quiet dots until hovered
    n.hit = (n.named || near || hot > 0.1)
      ? pill(P, nodeShort(n), n.color, hot > 0.1, n.px < 0 ? -1 : 1)
      : null;
    ctx.globalAlpha = 1;
    if (inRect(n.hit, mouse.x, mouse.y) || near) hoverNode = { n, P };
  });

  // faculty stations — colour-edged pills, always named (they are the diagram)
  chips.forEach(c => {
    const P = S(c.x, c.y);
    const hot = glow["chip:" + c.id] || 0;
    const r = 3.4 + hot * 3;
    ctx.fillStyle = c.color; ctx.shadowColor = c.color; ctx.shadowBlur = 8 + hot * 16;
    ctx.beginPath(); ctx.arc(P.X, P.Y, r, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.beginPath(); ctx.arc(P.X, P.Y, r * 0.34, 0, 7); ctx.fill();
    c.hit = pill(P, c.label.toUpperCase(), c.color, hot > 0.1, c.x < 0 ? -1 : 1, true);
    if (inRect(c.hit, mouse.x, mouse.y) || Math.hypot(P.X-mouse.x, P.Y-mouse.y) < 12) hoverChip = { c, P };
  });
  }   // end expert-only drawing

  // flowing thought particles + ripples
  stepStreams(dt);
  ripples = ripples.filter(r => r.a > 0.02);
  ripples.forEach(r => {
    r.r += 60 * dt; r.a *= 0.93;
    const P = S(r.x, r.y);
    ctx.strokeStyle = "rgba(126,200,255," + r.a + ")"; ctx.lineWidth = 1.2;
    if (MODE === "simple"){ hexPath(ctx, P.X, P.Y, r.r * cam.zoom, 0.26); ctx.stroke(); }
    else { ctx.beginPath(); ctx.arc(P.X, P.Y, r.r * cam.zoom, 0, 7); ctx.stroke(); }
  });

  // hover card
  hoverHold = !!(hoverNode || hoverChip);
  lastHover = hoverNode;                     // what a click would visit
  if (!cam.drag) cv.style.cursor = hoverNode ? "pointer" : "grab";
  if (hoverNode || hoverChip){
    const h = hoverNode || hoverChip;
    card.style.display = "block";
    card.style.left = Math.min(W - 320, h.P.X + 16) + "px";
    card.style.top  = Math.max(10, h.P.Y + 14) + "px";
    if (hoverNode){
      const n = hoverNode.n, meta = (LAND.types || {})[n.type] || {};
      // the relations, spelled out: which memories this one is really wired to
      const rel = [];
      gedges.forEach(l => {
        const o = l.a === n.idx ? gindex["n" + l.b] : (l.b === n.idx ? gindex["n" + l.a] : null);
        if (o) rel.push(o.label.length > 24 ? o.label.slice(0, 23) + "…" : o.label);
      });
      card.innerHTML = '<div class="t" style="color:' + n.color + '">' + (meta.label || n.type) + " memory</div>"
        + '<div>' + n.label + "</div>" + '<div class="m">' + (n.ts || "") + "</div>"
        + (rel.length
          ? '<div class="m" style="margin-top:4px">related — ' + rel.slice(0, 3).join(" · ")
            + (rel.length > 3 ? " · +" + (rel.length - 3) + " more" : "") + "</div>"
          : '<div class="m" style="margin-top:4px">not yet related to anything</div>');
    } else {
      const c = hoverChip.c;
      card.innerHTML = '<div class="t" style="color:' + c.color + '">' + c.label + "</div>"
        + '<div class="m">' + c.role + "</div>"
        + (badge(c.id) ? '<div class="m" style="margin-top:3px">' + badge(c.id) + "</div>" : "");
    }
  } else card.style.display = "none";

  // honest empty state
  if (!nodes.length){
    ctx.fillStyle = "rgba(160,170,190,.6)"; ctx.font = "12px ui-monospace, Menlo, monospace"; ctx.textAlign = "center";
    ctx.fillText("no memories yet — talk with her, and this mind will fill", W/2, H*0.24);
    ctx.textAlign = "left";
  }

  // the instrument frame — corner ticks, like a well-made console
  // (bottom pair rides above the footer strip)
  ctx.strokeStyle = "rgba(170,190,230,0.28)"; ctx.lineWidth = 1;
  const M = 10, MB = 36, L = 16;
  [[M,M,1,1],[W-M,M,-1,1],[M,H-MB,1,-1],[W-M,H-MB,-1,-1]].forEach(([x,y,sx,sy]) => {
    ctx.beginPath();
    ctx.moveTo(x + sx*L, y); ctx.lineTo(x, y); ctx.lineTo(x, y + sy*L);
    ctx.stroke();
  });

  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>
"""


# /about — the story so far. Server-rendered; the changelog is the repo's real
# git history and the version is the real HEAD, so this page can never drift
# from the truth. Same instrument language as the Mind.
_ABOUT = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vera · The Story So Far</title>
<style>
  :root{ --mono: ui-monospace, "SF Mono", Menlo, monospace; }
  html{background:#04050a}
  body{margin:0;min-height:100vh;background:
    radial-gradient(ellipse at 50% -10%, #0a0e1c 0%, #04050a 55%);
    color:#dfe4ee;font-family:var(--mono);-webkit-font-smoothing:antialiased;
    padding-bottom:64px}
  a{color:#9fc6ef;text-decoration:none}
  a:hover{color:#bfe3ff}
  header{position:sticky;top:0;z-index:2;display:flex;align-items:center;gap:14px;
    padding:12px 18px;background:rgba(5,7,13,.92);backdrop-filter:blur(6px);
    border-bottom:1px solid rgba(170,190,230,.14);font-size:10px;
    letter-spacing:.12em;text-transform:uppercase}
  header .t{color:#eef2fa;border:1px solid rgba(170,190,230,.25);padding:5px 10px}
  header nav{display:flex;gap:14px;margin-left:auto}
  header nav a{color:rgba(175,190,220,.78)}
  main{max-width:740px;margin:0 auto;padding:34px 22px}
  h2{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#7ec8ff;
    margin:44px 0 6px;font-weight:600}
  h2:first-of-type{margin-top:8px}
  .sub{color:rgba(150,160,180,.75);font-size:11px;margin:0 0 18px}
  .pillar{display:flex;gap:12px;padding:10px 12px;margin:8px 0;font-size:12px;
    background:rgba(9,12,20,.6);border:1px solid rgba(170,190,230,.14);line-height:1.55}
  .pillar .dot{width:8px;height:8px;border-radius:50%;flex:none;margin-top:5px}
  .pillar b{color:#eef2fa;font-weight:600}
  .pillar span{color:#aeb4c0}
  /* the lifecycle — the same chain language the thought uses */
  .step{display:flex;gap:12px;align-items:baseline;font-size:12px;line-height:1.6;margin:2px 0}
  .step .n{width:20px;height:20px;border-radius:50%;border:1px solid rgba(126,200,255,.5);
    color:#bfe3ff;display:inline-flex;align-items:center;justify-content:center;
    font-size:9.5px;flex:none;transform:translateY(3px)}
  .step div{color:#aeb4c0}
  .step b{color:#eef2fa;font-weight:600}
  .stepline{width:1px;height:12px;background:rgba(126,200,255,.3);margin-left:10px}
  /* the changelog — the repo speaking for itself */
  #log{border-left:1px solid rgba(170,190,230,.18);padding-left:16px}
  #log .day{color:#7fd1b9;font-size:10px;letter-spacing:.12em;margin:16px 0 4px}
  #log .day:first-child{margin-top:2px}
  #log .entry{color:#c6ccd9;font-size:12px;line-height:1.65;padding:1px 0}
  #log .entry::before{content:"· ";color:rgba(150,160,180,.5)}
  pre.map{background:rgba(9,12,20,.6);border:1px solid rgba(170,190,230,.14);
    padding:16px;font-size:11.5px;line-height:1.7;color:#c6ccd9;overflow-x:auto}
  pre.map b{color:#eef2fa}
  pre.map i{color:rgba(150,160,180,.7);font-style:normal}
  #footer{position:fixed;left:0;right:0;bottom:0;height:26px;z-index:3;
    display:flex;align-items:center;gap:16px;padding:0 16px;
    background:rgba(5,7,13,.9);border-top:1px solid rgba(170,190,230,.14);
    backdrop-filter:blur(6px);font-size:9.5px;letter-spacing:.1em;
    text-transform:uppercase;color:rgba(150,160,180,.6)}
  #footer a{color:rgba(175,190,220,.78)}
  #footer .sp{flex:1}
  #footer .ver{color:rgba(150,160,180,.42)}
</style></head><body>
<header>
  <span class="t">VERA — THE STORY SO FAR</span>
  <nav>
    <a href="/">← her mind</a>
    <a href="#built">built</a>
    <a href="#changelog">changelog</a>
    <a href="#ship">how it ships</a>
    <a href="#map">site map</a>
  </nav>
</header>
<main>
  <h2 id="built">what we've built so far</h2>
  <p class="sub">a twin that lives on this machine — everything below is running now, none of it leaves 127.0.0.1</p>
  <div class="pillar"><span class="dot" style="background:#cfd8f2"></span><div><b>the mind, visible.</b> <span>her consciousness is a real fluid simulation (a hand-ported lattice-Boltzmann churn), her memories are cells constellated around it, their relations are threads, and a thought is light you can watch move. Nothing drawn is invented — every label is her real state.</span></div></div>
  <div class="pillar"><span class="dot" style="background:#7fd1b9"></span><div><b>memory that holds.</b> <span>everything she keeps is typed (emotion · task · opinion · knowledge), related, weighted by how often it truly returns in her thinking, and prunable when it's junk.</span></div></div>
  <div class="pillar"><span class="dot" style="background:#7ec8ff"></span><div><b>thinking you can audit.</b> <span>ask her something and the chain of events plays out: heard → memories surface → connecting → choosing words, ending with the model her policy genuinely routed to.</span></div></div>
  <div class="pillar"><span class="dot" style="background:#ffd9a0"></span><div><b>a mind you can travel.</b> <span>approach flight on open, orbit with a thrown hand, click a memory to visit it, double-click to glide home. The entrance animation only plays when the view proves it is rendering correctly.</span></div></div>
  <div class="pillar"><span class="dot" style="background:#c98bff"></span><div><b>her inner life.</b> <span>persona, soul (reflections while you're away), mood, rhythms of the day, day-task shadows, and a voice — each a faculty on the wiring you can see in the details view.</span></div></div>
  <div class="pillar"><span class="dot" style="background:#f3c969"></span><div><b>private by design.</b> <span>zero dependencies, no build step, local-first: the engine serves only 127.0.0.1 and the pages work offline.</span></div></div>

  <h2 id="changelog">changelog — __COUNT__ changes and counting</h2>
  <p class="sub">this is the repository's real history, read live from git — not release notes written after the fact</p>
  <div id="log">
__LOG__
  </div>

  <h2 id="ship">how a change ships</h2>
  <p class="sub">the same lifecycle every time — the thought chain, applied to the software itself</p>
  <div class="step"><span class="n">1</span><div><b>a want, said plainly.</b> the owner asks in human words — "the brain view lacks wow", "design has to communicate this better".</div></div>
  <div class="stepline"></div>
  <div class="step"><span class="n">2</span><div><b>built small.</b> zero dependencies, no build step; one file owns the change so the whole thing stays holdable.</div></div>
  <div class="stepline"></div>
  <div class="step"><span class="n">3</span><div><b>proven before shown.</b> syntax checks, screenshots at true retina density with real data, a live sweep for runtime errors across every interaction. Broken things never animate.</div></div>
  <div class="stepline"></div>
  <div class="step"><span class="n">4</span><div><b>served locally.</b> the engine restarts on 127.0.0.1:7879; the app's windows pick it up on reopen. Nothing is deployed anywhere — this machine is production.</div></div>
  <div class="stepline"></div>
  <div class="step"><span class="n">5</span><div><b>recorded honestly.</b> a human-readable commit per change — the changelog above <i>is</i> that record, unedited.</div></div>

  <h2 id="map">site map — where everything lives</h2>
  <p class="sub">the whole information architecture, one screen</p>
  <pre class="map"><b>the mind</b>  /                      <i>the live view — simple by default</i>
  ├─ ?mode=simple | expert        <i>human view · instrument view ("details")</i>
  ├─ ask bar → watch the thought  <i>recall → connect → choose words</i>
  ├─ click a memory → visit it    <i>camera keeps it centred; orbit around it</i>
  └─ ?demo=1 · ?yaw= · ?pitch=    <i>demos and screenshots</i>

<b>the story</b>  /about               <i>this page — built · changelog · lifecycle · map</i>

<b>the engine</b>  /api/*  <i>(127.0.0.1 only — the same data the pages draw)</i>
  ├─ /api/state                   <i>who she is right now</i>
  ├─ /api/landscape               <i>every memory, typed and related</i>
  ├─ /api/brain                   <i>faculties + real wiring</i>
  ├─ /api/thought?q=              <i>what a thought would really touch</i>
  └─ /api/route?q=                <i>the model the policy picks</i>

<b>the app</b>  Vera (macOS · iOS)     <i>Brain window = this Mind · voice at :7878</i></pre>
</main>
<div id="footer">
  <span>VERA · A MIND ON THIS MACHINE</span>
  <span class="sp"></span>
  <a href="/">the mind</a>
  <a href="#built">what's built</a>
  <a href="#changelog">changelog</a>
  <a href="#ship">how it ships</a>
  <a href="#map">site map</a>
  <span class="sp"></span>
  <span class="ver">build __VER__ · 127.0.0.1 only</span>
</div>
</body></html>
"""
