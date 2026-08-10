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
  <div class="foot">Runs locally. Close the tab to stop looking; the data stays sealed on disk.</div>
</div>
<div id="toast"></div>
<script>
const toastEl=document.getElementById("toast");
function toast(m,e){toastEl.textContent=m;toastEl.className="show"+(e?" err":"");setTimeout(()=>toastEl.className="",2200)}
const CONFIRM={booker_confirm:"Turn ON real bookings? The booker will make actual reservations on your account.",
 booker_nightly:"Schedule the booker to run automatically every night?"};
async function load(){
  const [life,ctrls]=await Promise.all([
    fetch("/api/life").then(r=>r.json()).catch(()=>({areas:[]})),
    fetch("/api/controls").then(r=>r.json()).catch(()=>({controls:[]}))]);
  renderLife(life.areas||[]);renderControls(ctrls.controls||[]);
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
        elif self.path == "/api/life":
            from . import life
            self._json(200, {"areas": life.snapshot()})
        elif self.path == "/api/controls":
            from . import controls
            self._json(200, {"controls": controls.snapshot()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/controls/set":
            from . import controls
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                data = {}
            r = controls.set_control((data.get("key") or "").strip(), bool(data.get("on")))
            self._json(200 if "error" not in r else 400, r)
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
