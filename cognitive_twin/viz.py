"""
Visualize Engine — *see how the twin thinks*, from real on-device data.

Most assistants are a black box. This serves one local page (127.0.0.1, never
exposed off the machine): **the Mind** — the whole app as a living galaxy,
rendered from the active twin's REAL state. The visual language is adapted from
the author's Universe Engine (sinhaankur.com — logarithmic spiral arms, orbit
trails whose bodies provably ride them, meteor pools, nebula fog), rebuilt here
in dependency-free 2D canvas so it needs no build step and works offline.

  - perceives — every memory is a star in a tilted spiral galaxy; each of the
    four memory types is an arm (emotion/task/opinion/knowledge), colored as in
    mem_types. Related memories are linked by faint filaments (landscape data).
  - how it works — the faculties (memory, persona, soul, mood, rhythms, shadow,
    router, voice) are planets on orbit rings around the twin's glowing core,
    each riding its own drawn trail, Kepler-style (closer = faster).
  - thinks — type a prompt and a comet flies the actual thought-path: through
    the memories it recalls for THAT prompt, then the faculties, into the model
    the routing policy really picks. Nothing is faked; empty log = empty sky.

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
    kind) — the data behind the universe view. Local only."""
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
    """Everything a real thought would touch, for the comet animation:
    the memories recall() actually surfaces for this prompt, the faculty path,
    and the model the policy really routes to. Honest — no invented steps."""
    out: dict[str, Any] = {"q": q}
    try:
        from . import memory
        hits = memory.recall(q, k=3)
        out["recall"] = [
            {"prompt": (e.get("prompt") or "").strip(),
             # trimmed exactly like brain.landscape() labels, so the client can
             # match a recalled memory to its star
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
def _page() -> bytes:
    return _PAGE.encode("utf-8")


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
        if self.path in ("/", "/index.html"):
            self._send(200, _page(), "text/html; charset=utf-8")
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
# works offline). Visual language adapted from the author's Universe Engine
# (sinhaankur.com); all data from the local APIs above.
_PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vera · The Mind</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#05060c;color:#e6e6e6;
    font-family:-apple-system,Segoe UI,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
  canvas{position:fixed;inset:0;display:block}
  .hud{position:fixed;pointer-events:none;z-index:2}
  #title{top:18px;left:22px}
  #title h1{margin:0;font-size:19px;font-weight:600;letter-spacing:.3px}
  #title .sub{color:#8f96a6;font-size:12.5px;margin-top:3px}
  #legend{bottom:18px;left:22px;display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:#aeb4c0}
  #legend .chip{display:inline-flex;align-items:center;gap:6px;background:rgba(13,16,28,.55);
    border:1px solid rgba(140,160,220,.12);border-radius:999px;padding:4px 10px;backdrop-filter:blur(6px)}
  #legend .dot{width:8px;height:8px;border-radius:50%}
  #askbar{bottom:18px;left:50%;transform:translateX(-50%);pointer-events:auto;display:flex;gap:8px}
  #askbar input{width:340px;background:rgba(13,16,28,.72);border:1px solid rgba(140,160,220,.22);
    color:#e6e6e6;border-radius:999px;padding:10px 16px;font-size:13px;outline:none;backdrop-filter:blur(8px)}
  #askbar input:focus{border-color:rgba(126,200,255,.6)}
  #askbar button{background:linear-gradient(135deg,#3b64ff,#7ec8ff);border:none;color:#fff;
    border-radius:999px;padding:10px 18px;font-size:13px;cursor:pointer}
  #hint{bottom:64px;left:50%;transform:translateX(-50%);color:#69708033;color:rgba(160,170,190,.45);font-size:11.5px}
  #card{display:none;background:rgba(10,12,22,.9);border:1px solid rgba(140,160,220,.25);border-radius:10px;
    padding:9px 12px;font-size:12.5px;max-width:300px;backdrop-filter:blur(8px);box-shadow:0 6px 24px rgba(0,0,0,.5)}
  #card .t{font-weight:600;margin-bottom:2px}
  #card .m{color:#8f96a6;font-size:11.5px}
  #answer{display:none;top:18px;right:22px;background:rgba(10,12,22,.88);border:1px solid rgba(126,200,255,.3);
    border-radius:12px;padding:12px 16px;font-size:12.5px;max-width:320px;backdrop-filter:blur(8px)}
  #answer .t{font-weight:600;color:#7ec8ff;margin-bottom:4px}
  #answer .row{color:#aeb4c0;margin-top:2px}
  #answer .kv{color:#7fd1b9}
</style></head><body>
<canvas id="sky"></canvas>
<div class="hud" id="title"><h1 id="who">The Mind</h1><div class="sub" id="stats">reading her real state…</div></div>
<div class="hud" id="legend"></div>
<div class="hud" id="hint">drag to pan · scroll to zoom · double-click to reset · hover anything · ask below and watch the thought travel</div>
<div class="hud" id="askbar"><input id="q" placeholder="ask her something — watch how the thought forms…"><button id="go">think</button></div>
<div class="hud" id="card"></div>
<div class="hud" id="answer"></div>
<script>
"use strict";
/* The Mind — the whole app as a living galaxy, in vanilla canvas.
   Visual language adapted from the author's Universe Engine (sinhaankur.com):
   logarithmic spiral arms (r = a·e^(bθ), b≈0.26), Kepler-ish orbit trails the
   bodies provably ride, a meteor pool (delay/flight/cooldown), nebula fog.
   Every star/planet is real local state — empty log means an empty sky. */

const cv = document.getElementById("sky"), ctx = cv.getContext("2d");
let W = 0, H = 0, DPR = 1;
function resize(){
  DPR = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  cv.width = W * DPR; cv.height = H * DPR;
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}
window.addEventListener("resize", resize); resize();

/* ---------- live data ------------------------------------------------------ */
let STATE = {}, LAND = {points:[],links:[],types:{}}, BRAIN = {nodes:[],edges:[],state:{}};
async function j(u){ return await (await fetch(u)).json(); }
async function loadAll(){
  try{ STATE = await j("/api/state"); }catch(_){}
  try{ LAND = await j("/api/landscape"); }catch(_){}
  try{ BRAIN = await j("/api/brain"); }catch(_){}
  buildGalaxy(); buildPlanets(); hudRefresh();
}
setInterval(loadAll, 12000); loadAll();

/* ---------- deterministic jitter (stable across repolls) ------------------- */
function rnd(i){ let t = (i + 1) * 0x6D2B79F5;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }

/* ---------- camera --------------------------------------------------------- */
const cam = { zoom: 1, ox: 0, oy: 0, drag: null };
const TILT = 0.55;                    // the galaxy leans back — reads as 3D
let OMEGA = 0;                        // slow global rotation of the disc
function S(x, y){ return { X: W/2 + (x*cam.zoom) + cam.ox, Y: H/2 + (y*cam.zoom) + cam.oy }; }

/* ---------- the memory galaxy (perceives) ---------------------------------- */
/* Four logarithmic arms, one per memory type; a star's distance along its arm
   is its age rank (older = nearer the core; new memories are born at the rim). */
const ARMS = { emotion:0, task:1, opinion:2, knowledge:3 };
const B = 0.26, SWEEP = 4.2;          // arm tightness + how far each arm winds
let stars = [];                       // {r,a0,size,color,type,label,ts,heat,tw}
function discR(){ return Math.min(W, H) * 0.40; }
function buildGalaxy(){
  const pts = LAND.points || [];
  const byType = {};
  pts.forEach((p, i) => { (byType[p.type] = byType[p.type] || []).push([p, i]); });
  stars = [];
  Object.keys(byType).forEach(type => {
    const arm = (ARMS[type] !== undefined ? ARMS[type] : 3) * (Math.PI / 2);
    const list = byType[type].sort((a, b) => (a[0].ts || "").localeCompare(b[0].ts || ""));
    const R = discR(), R0 = R / Math.exp(B * SWEEP);
    list.forEach(([p, i], k) => {
      const t = list.length > 1 ? k / (list.length - 1) : 0.6;
      const th = t * SWEEP;
      let r = R0 * Math.exp(B * th);
      r += (rnd(i * 3) - 0.5) * R * 0.13 * (0.5 + t * 0.5);      // arm dispersion
      const a0 = th + arm + (rnd(i * 3 + 1) - 0.5) * 0.32;
      stars.push({ idx: i, r, a0, type, label: p.label, ts: p.ts, heat: p.heat || 0,
                   color: p.color, size: 1.7 + Math.min(3.4, (p.heat || 0) * 2.6),
                   tw: rnd(i * 3 + 2) * 6.28 });
    });
  });
}
function starPos(s){                   // world position (rotates with the disc)
  const a = s.a0 + OMEGA;
  return { x: Math.cos(a) * s.r, y: Math.sin(a) * s.r * TILT, front: Math.sin(a) >= 0 };
}

/* ---------- the faculties as planets (how it works) ------------------------- */
const P_COLOR = { memory:"#7fd1b9", persona:"#ffd9a0", soul:"#c98bff", mood:"#ff7eb6",
  rhythms:"#8fb7ff", activity:"#9adf7c", shadow:"#f3c969", router:"#7ec8ff", voice:"#ff9e3d" };
let planets = [];                      // {id,label,role,orbit,phase,omega,color}
function buildPlanets(){
  const cores = (BRAIN.nodes || []).filter(n => n.kind === "core");
  const base = Math.min(W, H) * 0.085;
  planets = cores.map((n, i) => {
    const orbit = base + i * Math.min(W, H) * 0.033;
    const old = planets.find(p => p.id === n.id);
    return { id: n.id, label: n.label, role: n.role || "", orbit,
             phase: old ? old.phase : rnd(i * 7) * 6.28,
             omega: 0.0042 * Math.pow(base / orbit, 1.5),   // Kepler-ish: closer = faster
             color: P_COLOR[n.id] || "#9fb4ff" };
  });
}
function planetPos(p){
  return { x: Math.cos(p.phase) * p.orbit, y: Math.sin(p.phase) * p.orbit * TILT,
           front: Math.sin(p.phase) >= 0 };
}
function badge(p){
  const st = BRAIN.state || {};
  if (p.id === "memory")  return (st.memory_count || 0) + " memories";
  if (p.id === "shadow")  return (st.open_tasks || 0) + " open tasks";
  if (p.id === "rhythms") return st.part_of_day || "";
  if (p.id === "soul")    return (st.reflections || 0) + " thoughts waiting";
  return "";
}

/* ---------- ambience: dust, meteors, nebula --------------------------------- */
const dust = Array.from({length: 170}, (_, i) => ({
  x: rnd(i*11)*1.6-0.8, y: rnd(i*11+1)*1.6-0.8, z: 0.15+rnd(i*11+2)*0.85, r: 0.3+rnd(i*11+3)*1.2 }));
const meteors = Array.from({length: 4}, (_, i) => ({ t: -(i*3 + rnd(i)*5), dur: 0, cool: 0, a:{}, b:{} }));
function resetMeteor(m){
  const side = Math.random()*6.28, R = Math.max(W,H)*0.7;
  m.a = { x: Math.cos(side)*R, y: Math.sin(side)*R };
  m.b = { x: (Math.random()-0.5)*W*0.5, y: (Math.random()-0.5)*H*0.5 };
  m.dur = 1.6 + Math.random()*1.6; m.cool = 5 + Math.random()*11; m.t = 0;
}

/* ---------- the thought comet (thinks) -------------------------------------- */
let comet = null;                     // {legs, leg, t, pos, trail, route}
let ripples = [], floats = [];
function resolveLeg(l){
  if (l.kind === "point")  return l;
  if (l.kind === "star")   { const s = stars.find(s => s.idx === l.idx); if(!s) return {x:0,y:0};
                             const w = starPos(s); return { x:w.x, y:w.y }; }
  if (l.kind === "planet") { const p = planets.find(p => p.id === l.id); if(!p) return {x:0,y:0};
                             const w = planetPos(p); return { x:w.x, y:w.y }; }
  return { x: 0, y: 0 };
}
async function think(q){
  const A = document.getElementById("answer"); A.style.display = "none";
  let d; try{ d = await j("/api/thought?q=" + encodeURIComponent(q)); }catch(_){ return; }
  const legs = [{ kind:"point", x: -W*0.62, y: -H*0.18 }];
  (d.recall || []).forEach(r => {
    const s = stars.find(s => s.label === r.label);
    if (s) legs.push({ kind:"star", idx: s.idx, name: r.label });
  });
  (d.path || []).forEach(id => {
    if (planets.find(p => p.id === id)) legs.push({ kind:"planet", id, name: id });
  });
  legs.push({ kind:"point", x: 0, y: 0, name: "her answer forms" });
  comet = { legs, leg: 0, t: 0, pos: resolveLeg(legs[0]), trail: [], route: d.route || {} };
}
document.getElementById("go").onclick = () => { const q = document.getElementById("q").value.trim(); if (q) think(q); };
document.getElementById("q").addEventListener("keydown", e => { if (e.key === "Enter") document.getElementById("go").click(); });
function cometStep(dt){
  if (!comet) return;
  const next = comet.legs[comet.leg + 1];
  if (!next) {   // arrived — show the honest routing result
    const A = document.getElementById("answer"), r = comet.route || {};
    if (r.model){ A.innerHTML = '<div class="t">how she would answer</div>'
      + '<div class="row">model: <span class="kv">' + r.model + '</span></div>'
      + '<div class="row">rule: <span class="kv">' + (r.rule || "—") + '</span></div>'
      + '<div class="row">complexity ' + (r.complexity || "—") + ' · risk ' + (r.risk || "—") + '</div>'
      + '<div class="row" style="margin-top:4px;color:#8f96a6">routed locally — nothing left this machine</div>';
      A.style.display = "block"; }
    comet = null; return;
  }
  comet.t += dt / 0.85;
  const from = comet.pos, to = resolveLeg(next);
  const e = comet.t < 0.5 ? 2*comet.t*comet.t : 1 - Math.pow(-2*comet.t + 2, 2)/2;  // easeInOut
  const x = from.x + (to.x - from.x) * e, y = from.y + (to.y - from.y) * e;
  comet.trail.push({ x, y }); if (comet.trail.length > 26) comet.trail.shift();
  comet.cur = { x, y };
  if (comet.t >= 1){
    comet.pos = to; comet.leg++; comet.t = 0;
    ripples.push({ x: to.x, y: to.y, r: 4, a: 0.8 });
    if (next.name) floats.push({ text: next.name, x: to.x, y: to.y, life: 1 });
  }
}

/* ---------- interaction ----------------------------------------------------- */
let mouse = { x: -1, y: -1 };
const card = document.getElementById("card");
cv.addEventListener("mousemove", e => {
  mouse = { x: e.clientX, y: e.clientY };
  if (cam.drag){ cam.ox += e.clientX - cam.drag.x; cam.oy += e.clientY - cam.drag.y;
                 cam.drag = { x: e.clientX, y: e.clientY }; }
});
cv.addEventListener("mousedown", e => { cam.drag = { x: e.clientX, y: e.clientY }; cv.style.cursor = "grabbing"; });
window.addEventListener("mouseup", () => { cam.drag = null; cv.style.cursor = "grab"; });
cv.addEventListener("wheel", e => { e.preventDefault();
  const f = e.deltaY < 0 ? 1.1 : 1/1.1, nz = Math.max(0.5, Math.min(3.2, cam.zoom * f));
  cam.ox = (cam.ox) * (nz/cam.zoom); cam.oy = (cam.oy) * (nz/cam.zoom); cam.zoom = nz; }, { passive:false });
cv.addEventListener("dblclick", () => { cam.zoom = 1; cam.ox = 0; cam.oy = 0; });
cv.style.cursor = "grab";

/* ---------- HUD -------------------------------------------------------------- */
function hudRefresh(){
  const name = (STATE.persona && STATE.persona.name) || "your twin";
  document.getElementById("who").textContent = "The Mind — " + name;
  const st = BRAIN.state || {};
  const bits = [(STATE.memory_count || 0) + " memories"];
  if ((STATE.topics || []).length) bits.push("keeps returning to: " + STATE.topics.slice(0,3).join(", "));
  if (st.open_tasks) bits.push(st.open_tasks + " open tasks");
  if (STATE.part_of_day) bits.push(STATE.part_of_day);
  document.getElementById("stats").textContent = bits.join(" · ");
  const lg = document.getElementById("legend"); lg.innerHTML = "";
  Object.keys(LAND.types || {}).forEach(k => {
    const t = LAND.types[k]; if (!t || !t.count) return;
    const c = document.createElement("span"); c.className = "chip";
    c.innerHTML = '<span class="dot" style="background:' + t.color + ';box-shadow:0 0 6px ' + t.color + '"></span>'
                + t.label + " · " + t.count;
    lg.appendChild(c);
  });
}

/* ---------- render loop ------------------------------------------------------ */
let last = performance.now();
function frame(now){
  const dt = Math.min(0.05, (now - last) / 1000); last = now;
  OMEGA += dt * 0.021;                      // one slow turn every ~5 minutes
  planets.forEach(p => p.phase += p.omega * dt * 60);
  cometStep(dt);
  ctx.clearRect(0, 0, W, H);

  // deep-space vignette
  const bg = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, Math.max(W,H)*0.7);
  bg.addColorStop(0, "#0a0e1d"); bg.addColorStop(1, "#04050a");
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

  // parallax dust
  dust.forEach(d => {
    const px = W/2 + d.x*W*0.7 + cam.ox*d.z*0.35, py = H/2 + d.y*H*0.7 + cam.oy*d.z*0.35;
    ctx.globalAlpha = 0.10 + d.z*0.30; ctx.fillStyle = "#9fb4ff";
    ctx.beginPath(); ctx.arc(px, py, d.r, 0, 7); ctx.fill();
  });
  ctx.globalAlpha = 1;

  // nebula fog along each arm (additive, type-colored)
  ctx.globalCompositeOperation = "lighter";
  Object.keys(ARMS).forEach(type => {
    const meta = (LAND.types || {})[type]; if (!meta || !meta.count) return;
    const arm = ARMS[type] * (Math.PI/2), R = discR(), R0 = R/Math.exp(B*SWEEP);
    for (let k = 1; k <= 4; k++){
      const th = (k/4) * SWEEP, r = R0 * Math.exp(B*th), a = th + arm + OMEGA;
      const w = S(Math.cos(a)*r, Math.sin(a)*r*TILT);
      const RR = (30 + k*16) * cam.zoom;
      const g = ctx.createRadialGradient(w.X, w.Y, 0, w.X, w.Y, RR);
      g.addColorStop(0, meta.color + "16"); g.addColorStop(1, meta.color + "00");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(w.X, w.Y, RR, 0, 7); ctx.fill();
    }
  });
  ctx.globalCompositeOperation = "source-over";

  // filaments between related memories
  (LAND.links || []).forEach(l => {
    const a = stars.find(s => s.idx === l.a), b = stars.find(s => s.idx === l.b);
    if (!a || !b) return;
    const wa = starPos(a), wb = starPos(b), A = S(wa.x, wa.y), Bp = S(wb.x, wb.y);
    ctx.strokeStyle = "rgba(150,170,255," + (0.05 + (l.w || 0) * 0.16) + ")";
    ctx.lineWidth = 0.7; ctx.beginPath(); ctx.moveTo(A.X, A.Y); ctx.lineTo(Bp.X, Bp.Y); ctx.stroke();
  });

  // orbit trails (drawn ellipses the planets provably ride)
  planets.forEach(p => {
    ctx.strokeStyle = "rgba(126,200,255,0.10)"; ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.ellipse(W/2 + cam.ox, H/2 + cam.oy, p.orbit*cam.zoom, p.orbit*TILT*cam.zoom, 0, 0, 7);
    ctx.stroke();
  });

  // the flow diagram, always on: the app's real wiring between faculties,
  // drawn as faint living conduits with a slow pulse travelling source→target
  (BRAIN.edges || []).forEach((e, i) => {
    if (e.kind !== "wired") return;
    const a = planets.find(p => p.id === e.source), b = planets.find(p => p.id === e.target);
    if (!a || !b) return;
    const wa = planetPos(a), wb = planetPos(b);
    const A = S(wa.x, wa.y), Bp = S(wb.x, wb.y);
    ctx.strokeStyle = "rgba(140,160,220,0.07)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(A.X, A.Y); ctx.lineTo(Bp.X, Bp.Y); ctx.stroke();
    const ph = ((now * 0.00022) + i * 0.13) % 1;          // a mote flowing along
    const mx = A.X + (Bp.X - A.X) * ph, my = A.Y + (Bp.Y - A.Y) * ph;
    ctx.fillStyle = "rgba(160,185,255,0.34)";
    ctx.beginPath(); ctx.arc(mx, my, 1.3, 0, 7); ctx.fill();
  });

  // the core — her warm center, breathing
  const pulse = 1 + 0.06 * Math.sin(now * 0.0016);
  const core = S(0, 0), CR = Math.min(W,H) * 0.045 * cam.zoom * pulse;
  ctx.globalCompositeOperation = "lighter";
  for (const [rr, aa] of [[CR*3.4, 0.10], [CR*2.0, 0.22], [CR*1.1, 0.6]]){
    const g = ctx.createRadialGradient(core.X, core.Y, 0, core.X, core.Y, rr);
    g.addColorStop(0, "rgba(255,220,170," + aa + ")"); g.addColorStop(1, "rgba(255,220,170,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(core.X, core.Y, rr, 0, 7); ctx.fill();
  }
  ctx.globalCompositeOperation = "source-over";
  ctx.fillStyle = "rgba(255,246,230,.95)";
  ctx.beginPath(); ctx.arc(core.X, core.Y, CR*0.42, 0, 7); ctx.fill();
  ctx.fillStyle = "rgba(230,235,245,.8)"; ctx.font = "12px -apple-system,sans-serif"; ctx.textAlign = "center";
  ctx.fillText((STATE.persona && STATE.persona.name) || "her", core.X, core.Y + CR*3.4 + 14);
  ctx.textAlign = "left";

  // memory stars (back half first, then front, for depth)
  let hoverStar = null, hoverPlanet = null, best = 15;
  const drawStar = (s, front) => {
    const w = starPos(s); if (w.front !== front) return;
    const P = S(w.x, w.y);
    const tw = 0.7 + 0.3 * Math.sin(now * 0.003 + s.tw);
    const depth = front ? 1 : 0.55;
    const r = s.size * Math.sqrt(cam.zoom) * (front ? 1 : 0.8);
    const d = Math.hypot(P.X - mouse.x, P.Y - mouse.y);
    if (d < best){ best = d; hoverStar = { s, P }; }
    ctx.globalAlpha = depth;
    ctx.fillStyle = s.color; ctx.shadowColor = s.color; ctx.shadowBlur = 8 * tw;
    ctx.beginPath(); ctx.arc(P.X, P.Y, r, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
    ctx.fillStyle = "rgba(255,255,255," + (0.45 + 0.3*tw) + ")";
    ctx.beginPath(); ctx.arc(P.X, P.Y, Math.max(0.5, r*0.38), 0, 7); ctx.fill();
    ctx.globalAlpha = 1;
  };
  stars.forEach(s => drawStar(s, false));
  stars.forEach(s => drawStar(s, true));

  // planets riding their trails, with labels + live badges
  planets.forEach(p => {
    const w = planetPos(p), P = S(w.x, w.y);
    const r = (5.2 * (w.front ? 1 : 0.8)) * Math.sqrt(cam.zoom);
    const d = Math.hypot(P.X - mouse.x, P.Y - mouse.y);
    if (d < 16){ hoverPlanet = { p, P }; }
    ctx.globalAlpha = w.front ? 1 : 0.6;
    ctx.fillStyle = p.color; ctx.shadowColor = p.color; ctx.shadowBlur = 10;
    ctx.beginPath(); ctx.arc(P.X, P.Y, r, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
    ctx.fillStyle = "rgba(220,226,240,.85)"; ctx.font = "11px -apple-system,sans-serif";
    ctx.fillText(p.label, P.X + r + 5, P.Y + 3);
    const b = badge(p);
    if (b){ ctx.fillStyle = "rgba(150,158,175,.7)"; ctx.font = "10px -apple-system,sans-serif";
            ctx.fillText(b, P.X + r + 5, P.Y + 15); }
    ctx.globalAlpha = 1;
  });

  // hovered planet → light its wired edges (the app's real anatomy)
  if (hoverPlanet){
    (BRAIN.edges || []).forEach(e => {
      if (e.kind !== "wired") return;
      if (e.source !== hoverPlanet.p.id && e.target !== hoverPlanet.p.id) return;
      const q = planets.find(x => x.id === (e.source === hoverPlanet.p.id ? e.target : e.source));
      if (!q) return;
      const wq = planetPos(q), Q = S(wq.x, wq.y);
      ctx.strokeStyle = "rgba(200,215,255,.4)"; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(hoverPlanet.P.X, hoverPlanet.P.Y); ctx.lineTo(Q.X, Q.Y); ctx.stroke();
    });
  }

  // meteors (pool: delay → flight → cooldown, like the engine's ShootingStars)
  meteors.forEach(m => {
    m.t += dt;
    if (m.t < 0) return;
    if (m.dur === 0 || m.t > m.dur + m.cool){ resetMeteor(m); return; }
    if (m.t > m.dur) return;
    const pr = m.t / m.dur;
    const x = W/2 + m.a.x + (m.b.x - m.a.x) * pr, y = H/2 + m.a.y + (m.b.y - m.a.y) * pr;
    const dx = (m.b.x - m.a.x), dy = (m.b.y - m.a.y), mg = Math.hypot(dx, dy) || 1;
    const fade = Math.sin(pr * Math.PI);
    const g = ctx.createLinearGradient(x, y, x - dx/mg*46, y - dy/mg*46);
    g.addColorStop(0, "rgba(255,255,255," + 0.5*fade + ")"); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.strokeStyle = g; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - dx/mg*46, y - dy/mg*46); ctx.stroke();
    ctx.fillStyle = "rgba(255,255,255," + 0.85*fade + ")";
    ctx.beginPath(); ctx.arc(x, y, 1.5, 0, 7); ctx.fill();
  });

  // the thought comet + trail + ripples + floating labels
  if (comet && comet.cur){
    const P = S(comet.cur.x, comet.cur.y);
    comet.trail.forEach((t, i) => {
      const T = S(t.x, t.y), a = (i / comet.trail.length) * 0.5;
      ctx.fillStyle = "rgba(126,200,255," + a + ")";
      ctx.beginPath(); ctx.arc(T.X, T.Y, 1 + i*0.09, 0, 7); ctx.fill();
    });
    ctx.fillStyle = "#dff0ff"; ctx.shadowColor = "#7ec8ff"; ctx.shadowBlur = 18;
    ctx.beginPath(); ctx.arc(P.X, P.Y, 3.6, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
  }
  ripples = ripples.filter(r => r.a > 0.02);
  ripples.forEach(r => {
    r.r += 60 * dt; r.a *= 0.93;
    const P = S(r.x, r.y);
    ctx.strokeStyle = "rgba(126,200,255," + r.a + ")"; ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.arc(P.X, P.Y, r.r * cam.zoom, 0, 7); ctx.stroke();
  });
  floats = floats.filter(f => f.life > 0);
  floats.forEach(f => {
    f.life -= dt * 0.55;
    const P = S(f.x, f.y);
    ctx.fillStyle = "rgba(223,240,255," + Math.max(0, f.life) + ")";
    ctx.font = "11.5px -apple-system,sans-serif";
    ctx.fillText(f.text, P.X + 10, P.Y - 10 - (1 - f.life) * 14);
  });

  // hover card
  if (hoverStar || hoverPlanet){
    const h = hoverStar || hoverPlanet;
    card.style.display = "block";
    card.style.left = Math.min(W - 320, h.P.X + 16) + "px";
    card.style.top  = Math.max(10, h.P.Y - 14) + "px";
    if (hoverStar){
      const s = hoverStar.s, meta = (LAND.types || {})[s.type] || {};
      card.innerHTML = '<div class="t" style="color:' + s.color + '">' + (meta.label || s.type) + "</div>"
        + '<div>' + s.label + "</div>" + '<div class="m">' + (s.ts || "") + "</div>";
    } else {
      card.innerHTML = '<div class="t" style="color:' + hoverPlanet.p.color + '">' + hoverPlanet.p.label + "</div>"
        + '<div class="m">' + hoverPlanet.p.role + "</div>"
        + (badge(hoverPlanet.p) ? '<div class="m" style="margin-top:3px">' + badge(hoverPlanet.p) + "</div>" : "");
    }
  } else card.style.display = "none";

  // empty sky, honestly
  if (!stars.length){
    ctx.fillStyle = "rgba(160,170,190,.6)"; ctx.font = "14px -apple-system,sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No memories yet — talk with her, and stars will be born here.", W/2, H*0.32);
    ctx.textAlign = "left";
  }

  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>
"""
