/* Vera — Siri-style front end.
 *
 * SiriWave (kopiro/siriwave) is the reactive voice wave. Listening uses the
 * browser's SpeechRecognition; the transcript is sent to the local agent at
 * /api/ask; the answer is shown and spoken back via /api/speak (macOS `say`).
 * The wave amplitude tracks state: idle (flat) → listening → thinking → speaking.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const elStatus = $("status");
  const elTranscript = $("transcript");
  const elAnswer = $("answer");
  const elMic = $("mic");
  const elMicDot = $("micdot");
  const elModelPill = $("modelPill");
  const typed = $("typed");
  const typedInput = $("typedInput");

  // --- SiriWave: the iOS-9 flowing curves ----------------------------------
  const wave = new SiriWave({
    container: $("wave"),
    width: $("wave").clientWidth,
    height: 180,
    style: "ios9",
    autostart: true,
    speed: 0.15,
    amplitude: 0.4,
    // iOS9 curve colours — the classic Siri blue/red/green trio
    iOS9Curves: undefined,
  });
  function setWave(amp, speed) {
    wave.setAmplitude(amp);
    if (speed != null) wave.setSpeed(speed);
  }
  setWave(0.25, 0.12); // resting — visible gentle motion

  function setStatus(s) { elStatus.textContent = s; }

  // --- health: show which model is in play ---------------------------------
  fetch("/api/health").then((r) => r.json()).then((h) => {
    elModelPill.textContent = h.model || "auto";
    if (!h.tts) setStatus("voice replies off (no macOS say) — text only");
  }).catch(() => {});

  // --- her VOICE state: never leave the user guessing why she's silent ------
  // A small indicator in the model pill area: warming (model loading) → ready,
  // or "system voice" if her neural voice isn't installed. Polls until ready.
  const elVoicePill = $("voicePill");
  function renderVoice(st) {
    if (!elVoicePill) return;
    const map = {
      ready:       { dot: "#34d399", text: "voice ready" },
      warming:     { dot: "#fbbf24", text: "warming her voice…" },
      unavailable: { dot: "#9aa6c4", text: "system voice" },
    };
    const m = map[st && st.state] || map.unavailable;
    elVoicePill.innerHTML =
      '<span class="vdot" style="background:' + m.dot + '"></span>' + m.text;
    elVoicePill.title = (st && st.detail) || "";
  }
  function pollVoice(tries) {
    fetch("/api/voice/status").then((r) => r.json()).then((st) => {
      renderVoice(st);
      // keep polling while she's still warming (the first model load is slow)
      if (st && st.state === "warming" && (tries || 0) < 60) {
        setTimeout(() => pollVoice((tries || 0) + 1), 1500);
      }
    }).catch(() => {});
  }
  pollVoice(0);

  // --- visible chat box -----------------------------------------------------
  const elChat = document.getElementById("chat");
  function bubble(role, text, cls) {
    const d = document.createElement("div");
    d.className = "msg " + role + (cls ? " " + cls : "");
    d.textContent = text;
    elChat.appendChild(d);
    elChat.scrollTop = elChat.scrollHeight;
    return d;
  }
  function showSources(hits) {
    if (!hits || !hits.length) return;
    const row = document.createElement("div");
    row.className = "sources";
    const seen = new Set();
    for (const h of hits) {
      const key = (h.source || h.index) + "";
      if (seen.has(key)) continue;
      seen.add(key);
      const chip = document.createElement("span");
      chip.className = "src-chip";
      chip.title = (h.text || "").slice(0, 200);
      chip.innerHTML = `<b>${h.index}</b> · ${(h.source || "").split("/").pop()} · ${Math.round((h.score || 0) * 100)}%`;
      row.appendChild(chip);
    }
    elChat.appendChild(row);
    elChat.scrollTop = elChat.scrollHeight;
  }

  // --- talk to the agent ----------------------------------------------------
  async function ask(text) {
    if (!text) return;
    elTranscript.textContent = text;
    elAnswer.textContent = "";
    bubble("you", text);
    const thinking = bubble("vera", "thinking…", "thinking");
    setStatus("thinking…");
    setWave(0.04, 0.05); // quiet, slow shimmer while thinking

    // In parallel: the RAG sources that would ground this answer, so the chat
    // SHOWS what was retrieved (the "visible RAG" part), across all indexes.
    const ragP = fetch("/api/rag", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => r.json()).catch(() => ({ hits: [] }));

    // "How she thinks": the full legible pipeline (retrieval + feeling + path)
    // for the 🧠 panel, so the Mind is comprehensible, not a noisy galaxy.
    fetch("/api/thought", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => r.json()).then((t) => { if (window.renderMind) window.renderMind(t); }).catch(() => {});

    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      const answer = data.answer || "(no answer)";
      if (data.route && data.route.model) elModelPill.textContent = data.route.model;
      thinking.classList.remove("thinking");
      thinking.textContent = answer;
      elAnswer.textContent = answer;
      const rag = await ragP;
      showSources(rag.hits);
      speak(answer);
    } catch (e) {
      thinking.classList.remove("thinking");
      thinking.textContent = "couldn't reach the agent";
      setStatus("couldn't reach the agent");
      setWave(0.12, 0.1);
    }
  }

  // --- speak the answer back (local say via the server) ---------------------
  function speak(text) {
    setStatus("speaking…");
    setWave(0.28, 0.18); // lively while speaking
    fetch("/api/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).catch(() => {});
    // We don't get an end event from server-side say; settle the wave after a
    // rough estimate tied to length, then return to rest.
    const ms = Math.min(12000, 900 + text.length * 45);
    clearTimeout(speak._t);
    speak._t = setTimeout(() => { setStatus("tap to speak"); setWave(0.12, 0.1); }, ms);
  }

  // --- listening (browser SpeechRecognition) -------------------------------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recog = null;
  let listening = false;

  function startListening() {
    if (!SR) {
      setStatus("speech input not supported here — type instead");
      showTyped(true);
      return;
    }
    recog = new SR();
    recog.lang = "en-US";
    recog.interimResults = true;
    recog.maxAlternatives = 1;

    listening = true;
    elMic.classList.add("listening");
    elMic.firstChild.nextSibling.textContent = " Listening…";
    elMicDot.classList.add("on");
    setStatus("listening…");
    setWave(0.5, 0.22); // big, fast while you talk

    let finalText = "";
    recog.onresult = (ev) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) finalText += t;
        else interim += t;
      }
      elTranscript.textContent = (finalText + interim).trim();
    };
    recog.onerror = () => { setStatus("didn't catch that"); stopUI(); };
    recog.onend = () => {
      stopUI();
      const text = elTranscript.textContent.trim();
      if (text) ask(text);
      else { setStatus("tap to speak"); setWave(0.12, 0.1); }
    };
    recog.start();
  }

  function stopListening() { if (recog) recog.stop(); }

  function stopUI() {
    listening = false;
    elMic.classList.remove("listening");
    elMic.firstChild.nextSibling.textContent = " Speak";
    elMicDot.classList.remove("on");
  }

  elMic.addEventListener("click", () => {
    if (listening) stopListening();
    else startListening();
  });

  // --- typed fallback -------------------------------------------------------
  function showTyped(on) { typed.style.display = on ? "flex" : "none"; if (on) typedInput.focus(); }
  $("typeToggle").addEventListener("click", () => showTyped(typed.style.display !== "flex"));
  typed.addEventListener("submit", (e) => {
    e.preventDefault();
    const t = typedInput.value.trim();
    typedInput.value = "";
    if (t) ask(t);
  });

  // keep the wave sized to the canvas on resize
  window.addEventListener("resize", () => {
    $("wave").width = $("wave").clientWidth;
  });

  // Auto-listen if the URL says so (menubar launches with ?listen=1)
  if (new URLSearchParams(location.search).get("listen") === "1") {
    setTimeout(startListening, 500);
  }
})();
