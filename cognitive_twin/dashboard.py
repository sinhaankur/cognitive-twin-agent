"""
dashboard — a standalone local app, NO Vera assistant required.

A tiny self-contained web server (its own — it does NOT import Vera's voice/agent
stack) that opens a visual dashboard in your browser. It shows everything tracked
on this Mac (life.snapshot) and every automation toggle (controls.snapshot), and
lets you flip switches by clicking — no terminal needed. Built for people who
don't live in a CLI.

It reuses the standalone module logic directly (life.py, controls.py), so the same
engine backs it whether or not the assistant is installed. Everything stays
on-device; the server binds to localhost only.

Run:
    python3 -m cognitive_twin.dashboard            # opens http://127.0.0.1:8677
    python3 -m cognitive_twin.dashboard --port 9000 --no-open

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 8677


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your life — on this Mac</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(ellipse at 50% 0%,#14161f,#06070b 70%);color:#f4f5f7;
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
 padding:40px 16px 80px;min-height:100vh}
.wrap{max-width:680px;margin:0 auto}
h1{font-size:24px;font-weight:600;letter-spacing:-.01em}
.sub{color:#8b93a7;font-size:13px;margin:4px 0 26px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#7b839a;
 margin:24px 0 10px;font-weight:600}
.card{background:#12141c;border:1px solid #1e2130;border-radius:14px;overflow:hidden}
.item{display:flex;align-items:center;gap:14px;padding:14px 16px;border-top:1px solid #1a1d29}
.item:first-child{border-top:none}.item .meta{flex:1;min-width:0}
.item .label{font-weight:500}.item .desc{color:#8b93a7;font-size:12.5px;margin-top:2px}
.item.off .label{color:#9aa1b4}
.dot{width:9px;height:9px;border-radius:50%;background:#3a3f52;flex:none}.dot.on{background:#3ddc84}
.sw{position:relative;width:44px;height:26px;flex:none}.sw input{opacity:0;width:0;height:0}
.slider{position:absolute;inset:0;cursor:pointer;background:#2a2e3f;border-radius:26px;transition:.2s}
.slider::before{content:"";position:absolute;height:20px;width:20px;left:3px;top:3px;
 background:#f4f5f7;border-radius:50%;transition:.2s}
input:checked+.slider{background:#4d6ef0}input:checked+.slider::before{transform:translateX(18px)}
input:disabled+.slider{cursor:not-allowed;opacity:.5}
.ro{font-size:12px;color:#6f7789}.tag{font-size:10px;text-transform:uppercase;letter-spacing:.06em;
 color:#f0a868;border:1px solid #4a3a24;border-radius:6px;padding:2px 6px;margin-left:6px}
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1e2130;
 border:1px solid #2a2e3f;padding:10px 16px;border-radius:10px;font-size:13px;opacity:0;
 transition:.25s;pointer-events:none}#toast.show{opacity:1}#toast.err{border-color:#5a2a2a;color:#f0a0a0}
.foot{color:#6f7789;font-size:12px;margin-top:28px;text-align:center}
</style></head><body>
<div class="wrap">
  <h1>Your life</h1>
  <div class="sub">Everything tracked on this Mac — sealed, private, no account. Nothing here has left your machine.</div>
  <h2>Now</h2><div class="card" id="life"></div>
  <div id="groups"></div>
  <h2>Automations</h2>
  <div class="card" style="padding:14px 16px">
    <div class="desc" style="margin-bottom:10px">Import an automation from a link or file. It's reviewed before it can run — nothing happens on import.</div>
    <div style="display:flex;gap:8px">
      <input id="recipeSrc" placeholder="https://…/recipe.json  or  /path/to/recipe.json"
        style="flex:1;background:#0c0e15;border:1px solid #2a2e3f;border-radius:8px;color:#f4f5f7;padding:8px 10px;font-size:13px">
      <button id="recipeImport" style="background:#4d6ef0;border:none;color:#fff;border-radius:8px;padding:8px 14px;cursor:pointer;font-size:13px">Import</button>
    </div>
  </div>
  <div class="card" id="automations" style="margin-top:10px"></div>
  <div class="foot">Runs locally. Close the tab to stop looking; the data stays sealed on disk.</div>
</div>
<div id="toast"></div>
<script>
const toastEl=document.getElementById("toast");
function toast(m,e){toastEl.textContent=m;toastEl.className="show"+(e?" err":"");setTimeout(()=>toastEl.className="",2200)}
const CONFIRM={booker_confirm:"Turn ON real bookings? The booker will make actual reservations on your account.",
 booker_nightly:"Schedule the booker to run automatically every night?"};
async function load(){
  const [life,ctrls,autos]=await Promise.all([
    fetch("/api/life").then(r=>r.json()).catch(()=>({areas:[]})),
    fetch("/api/controls").then(r=>r.json()).catch(()=>({controls:[]})),
    fetch("/api/automations").then(r=>r.json()).catch(()=>({automations:[]}))]);
  renderLife(life.areas||[]);renderControls(ctrls.controls||[]);renderAutomations(autos.automations||[]);
}
function renderAutomations(list){
  const el=document.getElementById("automations");
  if(!list.length){el.innerHTML='<div class="item off"><div class="meta"><div class="desc">No automations yet. Import one above.</div></div></div>';return}
  el.innerHTML="";
  for(const a of list){
    const d=document.createElement("div");d.className="item";
    const warn=a.sensitive?'<span class="tag">sensitive</span>':"";
    const badge=a.approved?'<span class="ro" style="color:#3ddc84">approved</span>':'<span class="ro" style="color:#f0a868">needs review</span>';
    d.innerHTML=`<div class="meta"><div class="label">${a.name}${warn} ${badge}</div>
      <div class="desc">${a.description||""} · ${a.steps} step(s)${a.targets.length?" · "+a.targets[0]:""}</div></div>`;
    const btns=document.createElement("div");btns.style.cssText="display:flex;gap:6px";
    const mk=(txt,fn)=>{const b=document.createElement("button");b.textContent=txt;
      b.style.cssText="background:#1e2130;border:1px solid #2a2e3f;color:#d6dae6;border-radius:7px;padding:6px 10px;cursor:pointer;font-size:12px";
      b.onclick=fn;return b};
    btns.appendChild(mk("Review",()=>alert(a.review)));
    if(!a.approved)btns.appendChild(mk("Approve",()=>approveAuto(a.name)));
    btns.appendChild(mk("Dry-run",()=>runAuto(a.name,false)));
    if(a.approved)btns.appendChild(mk("Run",()=>{if(confirm("Run “"+a.name+"”? It will act in a browser."))runAuto(a.name,true)}));
    d.appendChild(btns);el.appendChild(d);
  }
}
async function importAuto(){
  const src=document.getElementById("recipeSrc").value.trim();if(!src)return;
  const r=await fetch("/api/automations/import",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({source:src})}).then(r=>r.json()).catch(()=>({error:"network error"}));
  if(r.error)toast(r.error,true);else{toast("Imported “"+r.name+"” — review it");document.getElementById("recipeSrc").value="";load()}
}
async function approveAuto(name){
  await fetch("/api/automations/approve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});
  toast("Approved “"+name+"”");load();
}
async function runAuto(name,go){
  const r=await fetch("/api/automations/run",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({name,go})}).then(r=>r.json()).catch(()=>({error:"network error"}));
  if(r.error)toast(r.error,true);
  else if(r.status==="dry-run")alert(r.plan);
  else toast("Ran “"+name+"”: "+(r.steps||0)+" step(s)");
}
function renderLife(areas){
  const el=document.getElementById("life");el.innerHTML="";
  for(const a of areas){
    const d=document.createElement("div");d.className="item"+(a.on?"":" off");
    d.innerHTML=`<span class="dot ${a.on?"on":""}"></span>
      <div class="meta"><div class="label">${a.title}</div>
      <div class="desc">${a.headline||""}${a.detail?" — "+a.detail:""}</div></div>`;
    el.appendChild(d);
  }
}
function renderControls(controls){
  const byGroup={};for(const c of controls)(byGroup[c.group]||=[]).push(c);
  const wrap=document.getElementById("groups");wrap.innerHTML="";
  for(const[group,items]of Object.entries(byGroup)){
    const h=document.createElement("h2");h.textContent=group;wrap.appendChild(h);
    const card=document.createElement("div");card.className="card";
    for(const c of items)card.appendChild(itemEl(c));wrap.appendChild(card);
  }
}
function itemEl(c){
  const el=document.createElement("div");el.className="item"+(c.on?"":" off");
  const ctl=c.readonly
    ?`<span class="dot ${c.on?"on":""}"></span><span class="ro">${c.on?"yes":"—"}</span>`
    :`<label class="sw"><input type="checkbox" ${c.on?"checked":""} ${c.available?"":"disabled"}><span class="slider"></span></label>`;
  const warn=c.key.startsWith("booker_")?`<span class="tag">outward</span>`:"";
  el.innerHTML=`<div class="meta"><div class="label">${c.label}${warn}</div>
    <div class="desc">${c.description||""}</div></div>${ctl}`;
  const inp=el.querySelector("input");if(inp)inp.addEventListener("change",()=>toggle(c,inp));
  return el;
}
async function toggle(c,inp){
  const on=inp.checked;
  if(on&&CONFIRM[c.key]&&!confirm(CONFIRM[c.key])){inp.checked=false;return}
  const r=await fetch("/api/controls/set",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({key:c.key,on})}).then(r=>r.json()).catch(()=>({error:"network error"}));
  if(r.error){inp.checked=!on;toast(r.error,true)}else{toast(`${r.label}: ${r.on?"on":"off"}`);load()}
}
document.getElementById("recipeImport").addEventListener("click",importAuto);
load();setInterval(load,15000);
</script></body></html>"""


# ── NEW: Tailscale-quality settings (side-by-side at /settings; reference impl for
#    every platform). Renders purely from controls.snapshot() — tabs, groups,
#    toggles, typed-confirm for danger rows. Current "/" dashboard is untouched. ──
SETTINGS_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vera — Settings</title>
<style>
:root{
 --bg:#f6f6f5;--panel:#fff;--ink:#1a1a19;--muted:#6b6b66;--line:#ececea;
 --accent:#10a37f;--accent-ink:#0a7f63;--accent-soft:#e8f7f1;
 --warn:#b06a00;--warn-soft:#fdf3e3;--danger:#c0392b;--danger-soft:#fbeceb;
 --radius:12px;--shadow:0 1px 2px rgba(0,0,0,.04);
}
@media (prefers-color-scheme:dark){:root{
 --bg:#17171a;--panel:#1f1f23;--ink:#ededed;--muted:#9b9b9b;--line:#2c2c31;
 --accent:#3ecf8e;--accent-ink:#3ecf8e;--accent-soft:#16342a;
 --warn:#e0a44a;--warn-soft:#2e2615;--danger:#e06a5e;--danger-soft:#2e1a18;
 --shadow:0 1px 2px rgba(0,0,0,.3);
}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);
 font:15px/1.5 -apple-system,"Inter","Segoe UI",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;padding:34px 16px 70px;min-height:100vh}
.wrap{max-width:640px;margin:0 auto}
.title{font-size:20px;font-weight:650;letter-spacing:-.01em;text-align:center}
.sub{color:var(--muted);font-size:12.5px;text-align:center;margin:3px 0 20px}
.tabs{display:flex;gap:4px;justify-content:center;margin-bottom:22px}
.tabs button{border:0;background:transparent;color:var(--muted);font:inherit;font-size:13.5px;
 font-weight:550;padding:7px 15px;border-radius:9px;cursor:pointer;display:flex;align-items:center;gap:6px}
.tabs button.sel{background:var(--panel);color:var(--ink);box-shadow:var(--shadow);border:1px solid var(--line)}
.group{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
 font-weight:600;margin:20px 4px 8px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
 overflow:hidden;box-shadow:var(--shadow)}
.row{display:flex;align-items:center;gap:14px;padding:13px 16px;border-top:1px solid var(--line)}
.row:first-child{border-top:none}
.row .meta{flex:1;min-width:0}
.row .label{font-weight:550;font-size:14.5px}
.row .desc{color:var(--muted);font-size:12.5px;margin-top:2px}
.row.off .label{color:var(--muted)}
.row.na{opacity:.55}
.badge{font-size:10px;text-transform:uppercase;letter-spacing:.05em;padding:2px 7px;border-radius:6px;
 margin-left:7px;vertical-align:1px;border:1px solid var(--line);color:var(--muted)}
.badge.danger{color:var(--danger);border-color:transparent;background:var(--danger-soft)}
.badge.on{color:var(--accent-ink);border-color:transparent;background:var(--accent-soft)}
.manage{font-size:12.5px;color:var(--accent-ink);background:transparent;border:1px solid var(--line);
 border-radius:8px;padding:5px 11px;cursor:pointer;font-weight:550}
.sw{position:relative;width:42px;height:25px;flex:none}
.sw input{opacity:0;width:0;height:0}
.slider{position:absolute;inset:0;cursor:pointer;background:var(--line);border-radius:25px;transition:.18s}
.slider::before{content:"";position:absolute;height:19px;width:19px;left:3px;top:3px;background:#fff;
 border-radius:50%;transition:.18s;box-shadow:0 1px 2px rgba(0,0,0,.2)}
input:checked+.slider{background:var(--accent)}
input:checked+.slider::before{transform:translateX(17px)}
input:disabled+.slider{cursor:not-allowed;opacity:.45}
.ro{font-size:12px;color:var(--muted)}
.about .card{padding:18px}
.about .appname{font-size:16px;font-weight:650}
.about .ver{color:var(--muted);font-size:13px;margin-top:2px}
.about .line{display:flex;justify-content:space-between;padding:9px 0;border-top:1px solid var(--line);font-size:13.5px}
.about .line:first-of-type{border-top:0;margin-top:8px}
dialog{border:1px solid var(--line);border-radius:var(--radius);padding:0;background:var(--panel);
 color:var(--ink);max-width:400px;box-shadow:0 12px 44px rgba(0,0,0,.28)}
dialog::backdrop{background:rgba(0,0,0,.35)}
dialog .pad{padding:20px}dialog h3{font-size:16px;margin-bottom:7px}
dialog input[type=text]{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:8px;
 background:var(--bg);color:var(--ink);font:inherit;margin-top:10px}
.btnrow{display:flex;gap:9px;justify-content:flex-end;margin-top:16px}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:8px 13px;font:inherit;cursor:pointer}
button.primary{background:var(--accent);border:1px solid var(--accent);color:#fff;border-radius:8px;padding:8px 13px;font:inherit;font-weight:550;cursor:pointer}
#toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--panel);
 border:1px solid var(--line);padding:10px 16px;border-radius:10px;font-size:13px;opacity:0;
 transition:.22s;pointer-events:none;box-shadow:var(--shadow)}
#toast.show{opacity:1}#toast.err{border-color:var(--danger);color:var(--danger)}
.foot{color:var(--muted);font-size:11.5px;text-align:center;margin-top:26px}
.foot a{color:var(--accent-ink)}
</style></head><body>
<div class="wrap">
  <div class="title">Vera</div>
  <div class="sub">On-device · nothing here has left your Mac</div>
  <div class="tabs" id="tabs">
    <button data-tab="Settings" class="sel">Settings</button>
    <button data-tab="Connections">Connections</button>
    <button data-tab="About">About</button>
  </div>
  <div id="view"></div>
  <div class="foot">Same settings, every device. <a href="/">Classic view</a></div>
</div>
<dialog id="confirmDlg"><div class="pad">
  <h3 id="cfTitle">Confirm</h3>
  <p id="cfMsg" class="ro"></p>
  <input type="text" id="cfInput" placeholder="type ON to confirm" autocomplete="off">
  <div class="btnrow"><button class="ghost" id="cfCancel">Cancel</button><button class="primary" id="cfOk">Enable</button></div>
</div></dialog>
<div id="toast"></div>
<script>
const $=s=>document.querySelector(s);
const toastEl=$("#toast");
function toast(m,e){toastEl.textContent=m;toastEl.className="show"+(e?" err":"");setTimeout(()=>toastEl.className="",2200)}
let CONTROLS=[],TAB="Settings",pendingConfirm=null;

async function load(){
  const d=await fetch("/api/controls").then(r=>r.json()).catch(()=>({controls:[]}));
  CONTROLS=d.controls||[];render();
}
function render(){
  const view=$("#view");
  if(TAB==="About")return renderAbout(view);
  const inTab=CONTROLS.filter(c=>(c.tab||"Settings")===TAB);
  if(!inTab.length){view.innerHTML='<div class="card" style="padding:18px" class="ro">Nothing here yet.</div>';return}
  // group within the tab, preserving first-seen order
  const groups=[];const byG={};
  for(const c of inTab){if(!byG[c.group]){byG[c.group]=[];groups.push(c.group)}byG[c.group].push(c)}
  view.innerHTML=groups.map(g=>{
    const rows=byG[g].map(rowHTML).join("");
    return `<div class="group">${g}</div><div class="card">${rows}</div>`;
  }).join("");
  // wire toggles
  view.querySelectorAll("input[type=checkbox]").forEach(inp=>{
    inp.addEventListener("change",()=>onToggle(inp));
  });
}
function rowHTML(c){
  const na=!c.available;
  const cls="row"+(c.on?"":" off")+(na?" na":"");
  let right;
  if(c.type==="readonly"){
    right=`<span class="ro">${c.on?"Connected":"—"}</span>`;
  }else{
    right=`<label class="sw"><input type="checkbox" data-key="${c.key}" data-confirm="${c.confirm?encodeURIComponent(c.confirm):""}" data-danger="${c.danger?1:0}" ${c.on?"checked":""} ${na?"disabled":""}><span class="slider"></span></label>`;
  }
  const badge=c.danger?'<span class="badge danger">needs care</span>':(c.on&&c.type!=="readonly"?'<span class="badge on">on</span>':"");
  return `<div class="${cls}"><div class="meta"><div class="label">${c.label}${badge}</div><div class="desc">${c.description||""}</div></div>${right}</div>`;
}
function renderAbout(view){
  const conn=CONTROLS.filter(c=>c.type==="readonly");
  const lines=conn.map(c=>`<div class="line"><span>${c.label}</span><span class="ro">${c.on?"✓ connected":"—"}</span></div>`).join("");
  view.className="about";view.innerHTML=
    `<div class="card"><div class="appname">Vera</div><div class="ver">Cognitive twin · on-device · ${CONTROLS.length} controls</div>${lines}</div>`;
}
async function setControl(key,on){
  const r=await fetch("/api/controls/set",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({key,on,confirmed:true})}).then(r=>r.json()).catch(()=>({error:"network error"}));
  if(r.error){toast(r.error,true);load()}else{toast(`${r.label}: ${r.on?"on":"off"}`);load()}
}
function onToggle(inp){
  const key=inp.dataset.key,on=inp.checked;
  const confirm=inp.dataset.confirm?decodeURIComponent(inp.dataset.confirm):"";
  if(on&&confirm){ // dangerous ON → typed confirmation
    inp.checked=false; // revert visually until confirmed
    pendingConfirm={key};
    $("#cfTitle").textContent=document.querySelector(`[data-key="${key}"]`).closest(".row").querySelector(".label").textContent.replace(/needs care$/,"").trim();
    $("#cfMsg").textContent=confirm;$("#cfInput").value="";
    $("#confirmDlg").showModal();$("#cfInput").focus();
    return;
  }
  setControl(key,on);
}
$("#cfCancel").onclick=()=>{pendingConfirm=null;$("#confirmDlg").close()};
$("#cfOk").onclick=()=>{
  if($("#cfInput").value.trim().toUpperCase()!=="ON"){$("#cfInput").focus();return}
  const p=pendingConfirm;pendingConfirm=null;$("#confirmDlg").close();
  if(p)setControl(p.key,true);
};
$("#tabs").querySelectorAll("button").forEach(b=>b.onclick=()=>{
  TAB=b.dataset.tab;$("#tabs").querySelectorAll("button").forEach(x=>x.classList.toggle("sel",x===b));
  $("#view").className="";render();
});
load();setInterval(load,15000);
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path in ("/settings", "/settings.html"):
            # New Tailscale-style settings (side-by-side; "/" is unchanged).
            self._send(200, SETTINGS_PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/life":
            from . import life
            self._json(200, {"areas": life.snapshot()})
        elif self.path == "/api/controls":
            from . import controls
            self._json(200, {"controls": controls.snapshot()})
        elif self.path == "/api/automations":
            from .automations import recipe
            self._json(200, {"automations": [
                {"name": r.name, "description": r.description, "steps": len(r.steps),
                 "approved": r.approved, "sensitive": r.sensitive,
                 "targets": r.targets(), "review": recipe.review(r)}
                for r in recipe.read_all()]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except json.JSONDecodeError:
            data = {}
        if self.path == "/api/controls/set":
            from . import controls
            key = (data.get("key") or "").strip()
            on = bool(data.get("on"))
            # Danger controls (e.g. real bookings) require an explicit confirmed:true
            # — server-side guard so the UI's typed-confirm can't be bypassed.
            c = controls.get_control(key)
            if c is not None and on and getattr(c, "danger", False) and not data.get("confirmed"):
                self._json(409, {"error": "confirmation required", "confirm": c.confirm,
                                 "label": c.label, "needsConfirm": True})
                return
            r = controls.set_control(key, on)
            self._json(200 if "error" not in r else 400, r)
        elif self.path == "/api/automations/import":
            from .automations import recipe
            try:
                r = recipe.import_recipe((data.get("source") or "").strip())
                self._json(200, {"ok": True, "name": r.name, "review": recipe.review(r)})
            except recipe.RecipeError as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                self._json(400, {"error": f"couldn't import: {e}"})
        elif self.path == "/api/automations/approve":
            from .automations import recipe
            r = recipe.approve((data.get("name") or "").strip())
            self._json(200 if r else 404, {"ok": bool(r)})
        elif self.path == "/api/automations/run":
            # Dry-run by default; only runs when go=true (an approved recipe).
            from .automations import run
            try:
                r = run.run((data.get("name") or "").strip(), go=bool(data.get("go")))
                self._json(200, r)
            except run.RunError as e:
                self._json(400, {"error": str(e)})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, *_):  # quiet
        pass


def serve(port: int = DEFAULT_PORT, *, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((HOST, port), _Handler)
    url = f"http://{HOST}:{port}"
    print(f"Your life dashboard: {url}  (Ctrl-C to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.shutdown()


def _main(argv: list[str]) -> int:
    port = DEFAULT_PORT
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    serve(port, open_browser="--no-open" not in argv)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
