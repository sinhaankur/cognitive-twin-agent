"""
Visualize Engine — *see how the twin thinks*, from real on-device data.

Most assistants are a black box. This serves a small local page (127.0.0.1, never
exposed off the machine) that renders three live views of the active twin:

  1. Reasoning trace — for a sample query, the model the policy picks, the persona
     + memory it folds in, and the answer path.
  2. Knowledge graph — the topics the twin keeps seeing (from local memory) and
     the reflections it saved, as a connected web.
  3. Inner state — evolving familiarity, mood, rhythm, and pending reflections.

All data comes from the same on-device modules the agent uses (memory, soul, mood,
rhythms, router) — nothing is fabricated, nothing leaves the machine.

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


# The page renders entirely from /api/state + /api/route. Kept dependency-free
# (inline SVG + vanilla JS) so it works offline and needs no build step.
_PAGE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cognitive Twin · Visualize Engine</title>
<style>
  body{margin:0;background:#0b0c10;color:#e6e6e6;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:860px;margin:0 auto;padding:28px}
  h1{font-weight:600;font-size:22px;margin:0 0 4px}
  .sub{color:#8a8a8a;font-size:14px;margin-bottom:20px}
  .tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
  .tab{padding:8px 16px;border-radius:999px;background:#16181f;color:#9aa0aa;cursor:pointer;font-size:14px}
  .tab.active{background:#2b59ff;color:#fff}
  .panel{display:none}.panel.active{display:block}
  .card{background:#101218;border-radius:12px;padding:20px;margin-bottom:14px}
  svg{width:100%;height:auto;display:block}
  .cap{color:#8a8a8a;font-size:13px;margin-top:10px}
  input{background:#16181f;border:1px solid #2a2d36;color:#e6e6e6;border-radius:8px;padding:8px 12px;width:60%}
  button{background:#2b59ff;border:none;color:#fff;border-radius:8px;padding:8px 16px;cursor:pointer;margin-left:8px}
  .kv{color:#7fd1b9}.muted{color:#8a8a8a}.think{color:#f3c969}
  .empty{color:#6a6a6a;font-style:italic}
  .bar-bg{fill:#16181f}.row-t{fill:#e6e6e6;font-size:12px}
</style></head><body><div class="wrap">
  <h1>Visualize Engine</h1>
  <div class="sub" id="who">reading your twin…</div>
  <div class="tabs">
    <div class="tab active" data-p="trace">Reasoning trace</div>
    <div class="tab" data-p="graph">Knowledge graph</div>
    <div class="tab" data-p="soul">Inner state</div>
  </div>

  <div class="panel active" id="p-trace"><div class="card">
    <div style="margin-bottom:12px">
      <input id="q" placeholder="ask anything — e.g. delete all my files / what stack should I use?">
      <button id="go">trace it</button>
    </div>
    <svg viewBox="0 0 760 120" id="trace-svg"></svg>
    <div class="cap" id="trace-cap">Type a query to see which local model the policy routes it to, and why.</div>
  </div></div>

  <div class="panel" id="p-graph"><div class="card">
    <svg viewBox="0 0 760 320" id="graph-svg"></svg>
    <div class="cap">Topics you keep raising + thoughts saved while away — your twin's connected knowledge, from local memory.</div>
  </div></div>

  <div class="panel" id="p-soul"><div class="card">
    <svg viewBox="0 0 760 230" id="soul-svg"></svg>
    <div class="cap" id="soul-cap"></div>
  </div></div>
</div>
<script>
const SVGNS="http://www.w3.org/2000/svg";
let STATE={};
const $=s=>document.querySelector(s);
function el(n,a){const e=document.createElementNS(SVGNS,n);for(const k in a)e.setAttribute(k,a[k]);return e;}

// tabs
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
  t.classList.add("active");
  ["trace","graph","soul"].forEach(p=>$("#p-"+p).classList.toggle("active",p===t.dataset.p));
  if(t.dataset.p==="graph")drawGraph();
  if(t.dataset.p==="soul")drawSoul();
});

async function load(){
  STATE=await (await fetch("/api/state")).json();
  $("#who").textContent = (STATE.persona&&STATE.persona.name? "talking to "+STATE.persona.name : "twin: "+(STATE.twin||"default"))
     + " · "+(STATE.memory_count||0)+" memories · "+(STATE.reflections||[]).length+" pending thoughts";
  // If the brain is on screen, fold any new memories in as fresh neurons —
  // this is what makes the graph visibly grow while you use the twin.
  if($("#p-graph").classList.contains("active")) syncBrain();
}

// Re-poll gently so the brain grows on its own as new memories are recorded.
setInterval(()=>{ load().catch(()=>{}); }, 8000);

// ---- trace ----
async function trace(q){
  const r=await (await fetch("/api/route?q="+encodeURIComponent(q))).json();
  const svg=$("#trace-svg");svg.innerHTML="";
  if(r.error){$("#trace-cap").textContent="router unavailable: "+r.error;return;}
  const steps=[["your message",q.slice(0,22),"#2b59ff"],
    ["complexity",r.complexity+" / risk "+r.risk,"#f3c969"],
    ["rule",r.rule,"#c98bff"],
    ["model",r.model,"#2bbb6b"]];
  steps.forEach((s,i)=>{
    const x=20+i*185;
    const g=el("g",{});g.style.opacity=0;g.style.transition="opacity .4s";
    g.appendChild(el("rect",{x,y:40,width:160,height:46,rx:9,fill:"#16181f",stroke:s[2]}));
    const t1=el("text",{x:x+80,y:60,fill:"#e6e6e6","font-size":12,"text-anchor":"middle"});t1.textContent=s[0];
    const t2=el("text",{x:x+80,y:77,fill:s[2],"font-size":11,"text-anchor":"middle"});t2.textContent=s[1];
    g.appendChild(t1);g.appendChild(t2);svg.appendChild(g);
    if(i<3)svg.appendChild(el("line",{x1:x+160,y1:63,x2:x+185,y2:63,stroke:"#2a2d36","stroke-width":2}));
    setTimeout(()=>g.style.opacity=1,150+i*350);
  });
  $("#trace-cap").textContent="Routed locally by policy — no cloud. Lower risk/complexity → a fast model; higher → a deeper one.";
}
$("#go").onclick=()=>{const q=$("#q").value.trim();if(q)trace(q);};
$("#q").addEventListener("keydown",e=>{if(e.key==="Enter")$("#go").click();});

// ---- knowledge graph: a living brain --------------------------------------
// A force-directed constellation of memory nodes that breathes and drifts, and
// grows as new memories arrive. No libraries — a tiny spring/repulsion sim on
// requestAnimationFrame. Node identity is keyed by label so re-polls animate
// new neurons in and gone ones out, rather than snapping the whole graph.
const CX=380, CY=160;
let brain={nodes:[], byKey:{}, raf:0, t:0};

function brainModel(){
  // Build the desired node set from current state; sizes reflect memory weight.
  const topics=(STATE.topics||[]).slice(0,8);
  const refl=(STATE.reflections||[]).slice(0,3);
  const want=[];
  topics.forEach((t,i)=>want.push({
    key:"t:"+t, label:t, c:"#7fd1b9",
    r:18-Math.min(6,i)*1.1        // earlier (more frequent) topics are larger
  }));
  refl.forEach(t=>want.push({
    key:"r:"+t, label:(t.length>18?t.slice(0,18)+"…":t), c:"#c98bff", r:12
  }));
  return want;
}

function syncBrain(){
  const want=brainModel();
  const wantKeys=new Set(want.map(w=>w.key));
  // add new neurons near the hub with a gentle outward kick
  want.forEach((w,i)=>{
    let node=brain.byKey[w.key];
    if(!node){
      const a=Math.random()*2*Math.PI;
      node={...w, x:CX+Math.cos(a)*12, y:CY+Math.sin(a)*12,
            vx:Math.cos(a)*0.6, vy:Math.sin(a)*0.6, born:brain.t, appear:0};
      brain.byKey[w.key]=node; brain.nodes.push(node);
    } else { node.r=w.r; node.c=w.c; node.label=w.label; }
  });
  // drop neurons whose memory is gone
  brain.nodes=brain.nodes.filter(n=>wantKeys.has(n.key));
  brain.byKey={}; brain.nodes.forEach(n=>brain.byKey[n.key]=n);
}

function stepBrain(){
  brain.t++;
  const ns=brain.nodes, k=ns.length||1;
  for(let i=0;i<k;i++){
    const a=ns[i]; if(!a) continue;
    // spring toward an ideal orbit radius (keeps the constellation readable)
    const dx=a.x-CX, dy=a.y-CY, d=Math.hypot(dx,dy)||1;
    const ideal=95+ (i%2)*26;                 // two soft shells
    const pull=(ideal-d)*0.012;
    a.vx+=(dx/d)*pull; a.vy+=(dy/d)*pull;
    // pairwise repulsion so labels don't pile up
    for(let j=i+1;j<k;j++){
      const b=ns[j]; const ex=a.x-b.x, ey=a.y-b.y; const e=Math.hypot(ex,ey)||1;
      if(e<70){ const f=(70-e)/e*0.06; a.vx+=ex*f; a.vy+=ey*f; b.vx-=ex*f; b.vy-=ey*f; }
    }
    // a slow, breathing drift so the brain feels alive even at rest
    a.vx+=Math.cos(brain.t*0.01+i)*0.006;
    a.vy+=Math.sin(brain.t*0.012+i)*0.006;
    a.vx*=0.90; a.vy*=0.90;                    // damping
    a.x+=a.vx; a.y+=a.vy;
    if(a.appear<1) a.appear=Math.min(1,a.appear+0.05);   // fade/scale in
  }
}

function paintBrain(){
  const svg=$("#graph-svg"); if(!svg) return;
  svg.innerHTML="";
  if(!brain.nodes.length){
    const t=el("text",{x:CX,y:CY,fill:"#6a6a6a","font-size":14,"text-anchor":"middle"});
    t.textContent="No memories yet — talk with your twin to grow its brain.";
    svg.appendChild(t); return;
  }
  // synapses first (under the nodes)
  brain.nodes.forEach(n=>{
    svg.appendChild(el("line",{x1:CX,y1:CY,x2:n.x,y2:n.y,
      stroke:"#2a2d36","stroke-width":1.4,"stroke-opacity":0.6*n.appear}));
  });
  // hub: a soft breathing glow + core
  const glow=8*Math.sin(brain.t*0.05)+30;
  svg.appendChild(el("circle",{cx:CX,cy:CY,r:glow,fill:"#2b59ff","fill-opacity":0.10}));
  svg.appendChild(el("circle",{cx:CX,cy:CY,r:26,fill:"#2b59ff"}));
  const me=el("text",{x:CX,y:CY+4,fill:"#fff","font-size":12,"text-anchor":"middle"});
  me.textContent=(STATE.persona&&STATE.persona.name)||"you"; svg.appendChild(me);
  // neurons
  brain.nodes.forEach(n=>{
    const r=n.r*n.appear;
    svg.appendChild(el("circle",{cx:n.x,cy:n.y,r:r+4,fill:n.c,"fill-opacity":0.15*n.appear}));
    svg.appendChild(el("circle",{cx:n.x,cy:n.y,r,fill:n.c,"fill-opacity":0.92*n.appear}));
    const tx=el("text",{x:n.x,y:n.y+(n.y>CY?n.r+16:-n.r-9),fill:"#cfd3da",
      "font-size":11,"text-anchor":"middle","fill-opacity":n.appear});
    tx.textContent=n.label; svg.appendChild(tx);
  });
}

function loopBrain(){ stepBrain(); paintBrain(); brain.raf=requestAnimationFrame(loopBrain); }

function drawGraph(){
  syncBrain();
  if(!brain.raf) loopBrain();     // start the animation once; syncBrain feeds it live
}

// ---- inner state ----
let soulDone=false;
function drawSoul(){
  if(soulDone)return;soulDone=true;
  const svg=$("#soul-svg");svg.innerHTML="";
  const mem=STATE.memory_count||0;
  const fam=Math.min(1, mem/40); // familiarity grows with memories
  svg.appendChild(el("circle",{cx:130,cy:115,r:64,fill:"none",stroke:"#16181f","stroke-width":13}));
  const ring=el("circle",{cx:130,cy:115,r:64,fill:"none",stroke:"#2b59ff","stroke-width":13,
    "stroke-linecap":"round","stroke-dasharray":402,"stroke-dashoffset":402,transform:"rotate(-90 130 115)"});
  svg.appendChild(ring);
  const l1=el("text",{x:130,y:111,fill:"#e6e6e6","font-size":14,"text-anchor":"middle"});l1.textContent="familiarity";
  const l2=el("text",{x:130,y:131,fill:"#7fd1b9","font-size":12,"text-anchor":"middle"});l2.textContent=Math.round(fam*100)+"%";
  svg.appendChild(l1);svg.appendChild(l2);
  setTimeout(()=>{ring.style.transition="stroke-dashoffset 1.1s";ring.setAttribute("stroke-dashoffset",402*(1-fam));},120);
  const rows=[["part of day",STATE.part_of_day||"—","#f3c969"],
    ["mood reflective",STATE.mood_reflective===null?"—":(STATE.mood_reflective?"yes":"no"),"#7fd1b9"],
    ["pending thoughts",(STATE.reflections||[]).length,"#c98bff"]];
  rows.forEach((r,i)=>{
    const y=55+i*52;
    const t=el("text",{x:280,y,fill:"#e6e6e6","font-size":13});t.textContent=r[0];svg.appendChild(t);
    const v=el("text",{x:700,y,fill:r[2],"font-size":13,"text-anchor":"end"});v.textContent=r[1];svg.appendChild(v);
    svg.appendChild(el("rect",{x:280,y:y+8,width:420,height:8,rx:4,fill:"#16181f"}));
  });
  $("#soul-cap").textContent=STATE.soul_status||"Your twin's inner state — it grows the more you share.";
}

load();
</script></body></html>"""
