/* Twin Voice — Siri-style front end.
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

  // --- talk to the agent ----------------------------------------------------
  async function ask(text) {
    if (!text) return;
    elTranscript.textContent = text;
    elAnswer.textContent = "";
    setStatus("thinking…");
    setWave(0.04, 0.05); // quiet, slow shimmer while thinking
    try {
      const res = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      const answer = data.answer || "(no answer)";
      if (data.route && data.route.model) elModelPill.textContent = data.route.model;
      elAnswer.textContent = answer;
      speak(answer);
    } catch (e) {
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
