/* flow.js — Vera's opt-in presence sense.
   Shi-Tomasi "Good Features to Track" + pyramidal Lucas-Kanade optical flow,
   ported from the owner's engine at sinhaankur.com/lab/optical-flow
   (components/optical-flow/flow-core.ts) — no OpenCV, no WASM, no server.

   Privacy contract (same as the lab's, plus one rule):
   - the camera starts ONLY after an explicit click, and a preview is always
     visible while it runs — no silent watching
   - frames never leave this page; the server receives only a few derived
     MOTION facts per second: present, energy, nod/shake, lean
   - stopping posts /api/presence/stop so she forgets immediately            */
"use strict";

const Presence = (() => {

  /* ---------------- CV core (faithful port of flow-core.ts) --------------- */
  function toGray(img){
    const { data, width, height } = img;
    const out = new Float32Array(width * height);
    for (let i = 0, p = 0; i < out.length; i++, p += 4)
      out[i] = 0.299*data[p] + 0.587*data[p+1] + 0.114*data[p+2];   // Rec. 601
    return { data: out, width, height };
  }

  function blur(img){
    const { data, width: w, height: h } = img;
    const tmp = new Float32Array(w*h), out = new Float32Array(w*h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++){
      const i = y*w + x;
      const l = x > 0 ? data[i-1] : data[i], r = x < w-1 ? data[i+1] : data[i];
      tmp[i] = 0.25*l + 0.5*data[i] + 0.25*r;
    }
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++){
      const i = y*w + x;
      const u = y > 0 ? tmp[i-w] : tmp[i], d = y < h-1 ? tmp[i+w] : tmp[i];
      out[i] = 0.25*u + 0.5*tmp[i] + 0.25*d;
    }
    return { data: out, width: w, height: h };
  }

  function shiTomasi(img, opts){
    const { width: w, height: h } = img, block = opts.blockSize || 3;
    const gx = new Float32Array(w*h), gy = new Float32Array(w*h);
    const d = img.data;
    for (let y = 1; y < h-1; y++) for (let x = 1; x < w-1; x++){
      const i = y*w + x;
      gx[i] = (d[i+1] - d[i-1]) * 0.5;
      gy[i] = (d[i+w] - d[i-w]) * 0.5;
    }
    const score = new Float32Array(w*h);
    let maxScore = 0;
    for (let y = block; y < h-block; y++) for (let x = block; x < w-block; x++){
      let sxx = 0, syy = 0, sxy = 0;
      for (let wy = -block; wy <= block; wy++) for (let wx = -block; wx <= block; wx++){
        const j = (y+wy)*w + (x+wx), ix = gx[j], iy = gy[j];
        sxx += ix*ix; syy += iy*iy; sxy += ix*iy;
      }
      const t = sxx + syy, det = sxx*syy - sxy*sxy;
      const minEig = t/2 - Math.sqrt(Math.max(0, t*t/4 - det));   // min eigenvalue
      score[y*w + x] = minEig;
      if (minEig > maxScore) maxScore = minEig;
    }
    const thresh = maxScore * opts.qualityLevel;
    const cands = [];
    for (let y = block; y < h-block; y++) for (let x = block; x < w-block; x++){
      const s = score[y*w + x];
      if (s >= thresh && s > 0) cands.push({ x, y, age: 0, strength: s });
    }
    cands.sort((a, b) => b.strength - a.strength);
    // greedy non-max suppression on a grid
    const cell = Math.max(1, opts.minDistance), cols = Math.ceil(w/cell);
    const grid = new Map(), accepted = [], minD2 = opts.minDistance*opts.minDistance;
    for (const c of cands){
      if (accepted.length >= opts.maxCorners) break;
      const cx = (c.x/cell)|0, cy = (c.y/cell)|0;
      let close = false;
      for (let dy = -1; dy <= 1 && !close; dy++) for (let dx = -1; dx <= 1 && !close; dx++){
        const b = grid.get((cy+dy)*cols + (cx+dx));
        if (!b) continue;
        for (const p of b){
          const ddx = p.x-c.x, ddy = p.y-c.y;
          if (ddx*ddx + ddy*ddy < minD2){ close = true; break; }
        }
      }
      if (close) continue;
      accepted.push(c);
      const k = cy*cols + cx;
      (grid.get(k) || grid.set(k, []).get(k)).push(c);
    }
    return accepted;
  }

  function sample(img, x, y){
    const { data, width: w, height: h } = img;
    x = Math.max(0, Math.min(w-1, x)); y = Math.max(0, Math.min(h-1, y));
    const x0 = x|0, y0 = y|0, x1 = Math.min(x0+1, w-1), y1 = Math.min(y0+1, h-1);
    const fx = x-x0, fy = y-y0;
    return data[y0*w+x0]*(1-fx)*(1-fy) + data[y0*w+x1]*fx*(1-fy)
         + data[y1*w+x0]*(1-fx)*fy + data[y1*w+x1]*fx*fy;
  }

  function downsample(img){
    const w = img.width >> 1, h = img.height >> 1;
    const out = new Float32Array(w*h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++){
      const i = (y<<1)*img.width + (x<<1);
      out[y*w+x] = 0.25*(img.data[i] + img.data[i+1] + img.data[i+img.width] + img.data[i+img.width+1]);
    }
    return { data: out, width: w, height: h };
  }

  function buildPyramid(img, levels){
    const pyr = [img];
    for (let l = 1; l < levels; l++){
      const prev = pyr[l-1];
      if (prev.width < 16 || prev.height < 16) break;
      pyr.push(downsample(prev));
    }
    return pyr;
  }

  function trackPoint(prevPyr, nextPyr, px, py, win, iters){
    const levels = Math.min(prevPyr.length, nextPyr.length);
    let gx = 0, gy = 0;
    for (let l = levels-1; l >= 0; l--){
      const scale = 1/(1<<l), prev = prevPyr[l], next = nextPyr[l];
      const x = px*scale, y = py*scale;
      let vx = gx*scale, vy = gy*scale;
      for (let it = 0; it < iters; it++){
        let sxx = 0, syy = 0, sxy = 0, bx = 0, by = 0;
        for (let wy = -win; wy <= win; wy++) for (let wx = -win; wx <= win; wx++){
          const ax = x+wx, ay = y+wy;
          const it0 = sample(next, ax+vx, ay+vy) - sample(prev, ax, ay);
          const gix = (sample(prev, ax+1, ay) - sample(prev, ax-1, ay)) * 0.5;
          const giy = (sample(prev, ax, ay+1) - sample(prev, ax, ay-1)) * 0.5;
          sxx += gix*gix; syy += giy*giy; sxy += gix*giy;
          bx += -gix*it0; by += -giy*it0;
        }
        const det = sxx*syy - sxy*sxy;
        if (Math.abs(det) < 1e-6) break;
        const dvx = (syy*bx - sxy*by)/det, dvy = (sxx*by - sxy*bx)/det;
        vx += dvx; vy += dvy;
        if (dvx*dvx + dvy*dvy < 0.0009) break;
      }
      gx = vx/scale; gy = vy/scale;
    }
    const nx = px+gx, ny = py+gy, w0 = prevPyr[0].width, h0 = prevPyr[0].height;
    const ok = nx >= 0 && ny >= 0 && nx < w0 && ny < h0 && Math.hypot(gx, gy) < Math.max(w0, h0);
    return { x: nx, y: ny, ok };
  }

  /* ---------------- orchestrator + honest signal extraction ---------------- */
  const PW = 160, PH = 120;             // processing resolution
  const TARGET = 110, REDETECT_EVERY = 12;
  let stream = null, video = null, raf = 0, postTimer = 0;
  let prevPyr = null, points = [], frame = 0;
  let view = null, vctx = null;
  const proc = document.createElement("canvas"); proc.width = PW; proc.height = PH;
  const pctx = proc.getContext("2d", { willReadFrequently: true });

  // rolling window of per-frame motion stats (~1.5 s at ~20 fps)
  const hist = [];      // {dx, dy, mag, spread}
  const HIST = 30;

  function step(){
    raf = requestAnimationFrame(step);
    if (!video || video.readyState < 2) return;
    frame++;
    // mirror + downscale, like the lab
    pctx.save(); pctx.scale(-1, 1); pctx.drawImage(video, -PW, 0, PW, PH); pctx.restore();
    const gray = blur(toGray(pctx.getImageData(0, 0, PW, PH)));
    const pyr = buildPyramid(gray, 3);
    let dx = 0, dy = 0, mag = 0;
    if (prevPyr && points.length){
      const moved = [];
      for (const p of points){
        const r = trackPoint(prevPyr, pyr, p.x, p.y, 7, 8);
        if (!r.ok) continue;
        dx += r.x - p.x; dy += r.y - p.y; mag += Math.hypot(r.x - p.x, r.y - p.y);
        moved.push({ x: r.x, y: r.y, age: p.age + 1, strength: p.strength });
      }
      const n = Math.max(1, moved.length);
      dx /= n; dy /= n; mag /= n;
      points = moved;
    }
    if (points.length < TARGET * 0.7 || frame % REDETECT_EVERY === 0){
      const fresh = shiTomasi(gray, { maxCorners: TARGET, qualityLevel: 0.02, minDistance: 6 });
      // even-spacing merge: keep survivors, fill gaps with fresh corners
      for (const f of fresh){
        if (points.length >= TARGET) break;
        if (!points.some(p => (p.x-f.x)*(p.x-f.x) + (p.y-f.y)*(p.y-f.y) < 36)) points.push(f);
      }
    }
    prevPyr = pyr;
    // spread = median distance from centroid (grows when you lean in)
    let spread = 0;
    if (points.length > 4){
      let cx = 0, cy = 0;
      points.forEach(p => { cx += p.x; cy += p.y; });
      cx /= points.length; cy /= points.length;
      const ds = points.map(p => Math.hypot(p.x-cx, p.y-cy)).sort((a,b) => a-b);
      spread = ds[ds.length >> 1];
    }
    hist.push({ dx, dy, mag, spread });
    if (hist.length > HIST) hist.shift();
    draw();
  }

  function draw(){
    if (!vctx) return;
    const w = view.width, h = view.height;
    vctx.fillStyle = "#05060a"; vctx.fillRect(0, 0, w, h);
    vctx.globalCompositeOperation = "lighter";
    for (const p of points){
      const x = p.x/PW*w, y = p.y/PH*h;
      const a = Math.min(1, 0.25 + p.age*0.08);
      const r = 1.2 + Math.min(2, p.strength/1e4);
      const g = vctx.createRadialGradient(x, y, 0, x, y, r*3);
      const col = p.age < 6 ? "126,200,255" : (p.age < 20 ? "255,255,255" : "240,150,220");
      g.addColorStop(0, "rgba(" + col + "," + a + ")");
      g.addColorStop(1, "rgba(" + col + ",0)");
      vctx.fillStyle = g;
      vctx.beginPath(); vctx.arc(x, y, r*3, 0, 7); vctx.fill();
    }
    vctx.globalCompositeOperation = "source-over";
  }

  function signals(){
    if (hist.length < 10) return { present: false, energy: 0, gesture: null, lean: null };
    const present = points.length > 25;
    const mean = hist.reduce((s, x) => s + x.mag, 0) / hist.length;
    const energy = Math.max(0, Math.min(1, mean / 2.5));
    // nod/shake: oscillation — sign flips of the mean flow, per axis
    let flipsY = 0, flipsX = 0, ampY = 0, ampX = 0;
    for (let i = 1; i < hist.length; i++){
      const a = hist[i-1], b = hist[i];
      if (Math.abs(b.dy) > 0.35 && Math.abs(a.dy) > 0.35 && Math.sign(b.dy) !== Math.sign(a.dy)) flipsY++;
      if (Math.abs(b.dx) > 0.35 && Math.abs(a.dx) > 0.35 && Math.sign(b.dx) !== Math.sign(a.dx)) flipsX++;
      ampY = Math.max(ampY, Math.abs(b.dy)); ampX = Math.max(ampX, Math.abs(b.dx));
    }
    let gesture = null;
    if (flipsY >= 2 && ampY > ampX * 1.5) gesture = "nod";
    else if (flipsX >= 2 && ampX > ampY * 1.5) gesture = "shake";
    // lean: spread trend over the window
    const s0 = hist[0].spread || 1, s1 = hist[hist.length-1].spread || 1;
    let lean = null;
    if (s1 > s0 * 1.09) lean = "in";
    else if (s1 < s0 * 0.91) lean = "out";
    return { present, energy: Math.round(energy*100)/100, gesture, lean };
  }

  async function post(path, body){
    try{ await fetch(path, { method: "POST", headers: {"Content-Type": "application/json"},
                             body: JSON.stringify(body || {}) }); }catch(_){}
  }

  return {
    active: false,
    async start(canvas){
      if (this.active) return;
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 320, height: 240, facingMode: "user" }, audio: false });
      video = document.createElement("video");
      video.srcObject = stream; video.muted = true; video.playsInline = true;
      await video.play();
      view = canvas; vctx = canvas.getContext("2d");
      points = []; prevPyr = null; hist.length = 0; frame = 0;
      this.active = true;
      step();
      postTimer = setInterval(() => post("/api/presence", signals()), 1200);
    },
    stop(){
      if (!this.active) return;
      this.active = false;
      cancelAnimationFrame(raf); clearInterval(postTimer);
      if (stream) stream.getTracks().forEach(t => t.stop());
      stream = null; video = null; prevPyr = null; points = [];
      post("/api/presence/stop");        // she forgets immediately
    },
  };
})();
