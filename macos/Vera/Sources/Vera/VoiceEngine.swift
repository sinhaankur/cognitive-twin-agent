import Foundation
import AVFoundation
import Speech
import AppKit

/// Native, on-device voice: Apple's Speech framework for listening and
/// AVSpeechSynthesizer for talking back. No cloud, no extra dependencies.
///
/// The obsessive details (the things that make Siri feel finished):
///   - live partial transcript while you speak (published as `transcript`)
///   - semantic-ish endpointing: once you've said something and gone quiet
///     for ~0.9 s, the turn submits itself — no button needed
///   - barge-in: while she talks, the mic stays open in a muted hunt; words
///     that aren't HERS (echo-filtered against the utterance she's speaking)
///     cut her off and become the start of your next turn
///   - spectral sparkle: `brightness` tracks zero-crossing rate, so sibilants
///     flicker the orb's core while vowels swell its body
///   - per-word pulses while she speaks (`speakPulse`), soft synthesized
///     chimes on listen start / turn end (Chime.swift)
///
/// Publishes:
///   transcript   the recognized text (updates live while you speak)
///   level        mic loudness 0…1 (drives the orb amplitude)
///   brightness   0…1 spectral flicker (zero-crossing rate)
///   isListening / isSpeaking  state for the UI
@MainActor
final class VoiceEngine: ObservableObject {
    @Published var transcript: String = ""
    @Published var level: CGFloat = 0          // 0…1 mic amplitude
    @Published var brightness: CGFloat = 0     // 0…1 spectral flicker (ZCR)
    @Published var isListening = false
    @Published var isSpeaking = false
    @Published var authorized = false
    // True when the speech recognizer can't run on this machine right now, so the
    // UI can say so instead of the mic button silently toggling off.
    @Published var micUnavailable = false
    // True when a permission is needed and the macOS prompt didn't grant it. The
    // UI shows a calm, optional "Open Settings" button — we NEVER auto-jump to
    // Settings (that app↔Settings bounce is what froze things).
    @Published var permissionNeeded = false
    /// Bumped to 1 on every spoken word; the orb decays it (mouth-movement feel).
    var speakPulse: CGFloat = 0

    private let engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var didDeliverFinal = false   // guard: deliver onFinal once per turn
    private let synth = AVSpeechSynthesizer()
    // strong ref: AVSpeechSynthesizer.delegate is weak, so we must retain it or
    // the speaking-state callbacks (which light up the orb) never fire.
    private var speechDelegate: SpeechDelegate?

    // ---- Piper: Vera's bundled NEURAL voice (soft female, Her-like) ----
    // The brain synthesizes a WAV at /api/voice/piper; we play it HERE (the app
    // has the audio session the background service lacks). This is her default
    // voice when available; AVSpeechSynthesis is the fallback.
    @Published var piperEnabled = UserDefaults.standard.object(forKey: "vera.piperEnabled") as? Bool ?? true {
        didSet { UserDefaults.standard.set(piperEnabled, forKey: "vera.piperEnabled") }
    }
    var piperAvailable = false          // set from /api/health
    private var piperPlayer: AVAudioPlayer?
    private var piperDelegate: PiperPlayerDelegate?
    // Consecutive recognizer failures — caps the name-watch re-arm so a persistently
    // failing recognizer (ad-hoc TCC, missing on-device model) can't spin forever.
    private var recognizerFailures = 0

    // ---- endpointing state (main actor) ----
    private var listenStart = Date.distantPast
    private var sessionStart = Date.distantPast    // any session, incl. muted watches
    private var lastVoiceAt = Date.distantPast     // loud buffer OR transcript growth
    private var lastTranscriptLength = 0
    /// Endpointing tuning: how long a pause ends the turn, and the minimum
    /// turn age before we'd ever cut someone off mid-breath.
    private let endpointSilence: TimeInterval = 0.9
    private let endpointMinTurn: TimeInterval = 1.2

    // ---- barge-in state (main actor) ----
    /// muted = the mic is open only to hunt for interruption while she talks.
    private var muted = false
    private var echoWords: Set<String> = []        // words of HER current utterance
    private var displayFromSegment = 0             // barge turns: hide echo prefix
    private var externalSpeech = false             // cloned-voice playback in flight

    // ---- wake word (opt-in): her name, watched for while idle ----
    /// Fully local: the name watch never posts anywhere; it is a muted session
    /// whose ONLY trigger is the name itself. keepWatching survives turns so
    /// the app can re-arm the watch whenever she falls idle.
    private var nameWords: Set<String> = []
    private(set) var keepWatching = false

    /// Called when a final transcript is ready (user stopped talking).
    var onFinal: ((String) -> Void)?

    /// Voice isolation, only when needed: the ear (EarEngine) flips this while
    /// the room is noisy, and the NEXT listening session runs Apple's voice
    /// processing on the input — your voice lifted out of the bed before
    /// recognition. Quiet rooms keep the raw path (it's truer to the mic).
    var isolateVoice = false
    private var isolationApplied = false

    /// True while the room has a media bed (music / television) playing — set by
    /// EarEngine. When media is playing, the barge-in echo filter can't tell a
    /// YouTube narrator from YOU (it keys on text, not acoustics), so it would
    /// cut her off mid-sentence hearing the video as an interruption. While this
    /// is set we demand a much stronger, acoustic barge signal (real voice energy
    /// at the mic, right up close) instead of trusting transcribed words alone.
    var mediaNoisy = false

    init() {
        let delegate = SpeechDelegate(
            onChange: { [weak self] speaking in
                Task { @MainActor in self?.speakingChanged(speaking) }
            },
            onWord: { [weak self] in
                Task { @MainActor in self?.speakPulse = 1.0 }
            })
        speechDelegate = delegate
        synth.delegate = delegate

        // The #1 cause of "listening sometimes works, sometimes doesn't": a
        // route change (AirPods in/out, a display with speakers, another app
        // grabbing the device, a 44.1↔48 kHz sample-rate switch, sleep/wake)
        // leaves the engine's cached input format stale. A stopped engine then
        // throws on start(); a running one keeps the tap but the buffers stop
        // arriving (mic "on" but deaf). AVAudioEngine fires this when its own
        // config changes out from under it — rebind the live session on the new
        // hardware so it never silently goes deaf.
        NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.rebindAfterRouteChange() }
        }
    }

    /// The audio route changed under an active session. Rebuild it on the new
    /// hardware: a real listening turn restarts listening, a muted watch re-arms,
    /// a muted barge-hunt is simply dropped (her voice path restarts it).
    private func rebindAfterRouteChange() {
        guard isListening || muted else { return }   // nothing live → nothing to do
        let wasListening = isListening
        let names = Array(nameWords)
        let watching = keepWatching
        tearDownSession()
        isListening = false
        muted = false
        if wasListening {
            NSLog("[Vera voice] audio route changed mid-turn — rebinding the mic")
            startListening()
        } else if watching && !names.isEmpty {
            startNameWatch(names)
        }
    }

    /// Request BOTH permissions the voice pipeline needs: Speech Recognition
    /// AND microphone. The old version only asked for Speech — so on a fresh
    /// machine AVAudioEngine.start() failed (no mic access) and the mic button
    /// silently did nothing. Now both are requested; `authorized` is true only
    /// when speech + mic are both granted. Optional completion fires on the main
    /// actor so a caller can start listening the moment access lands.
    func requestPermission(_ completion: (@MainActor (Bool) -> Void)? = nil) {
        // LOCAL WHISPER: we need ONLY the microphone. Do NOT touch
        // SFSpeechRecognizer — on free-team / side-loaded builds, calling its
        // authorization API can abort the app under TCC ("crashed … without a
        // usage description"), which caused a crash-relaunch LOOP. Mic only.
        if useLocalWhisper {
            AVCaptureDevice.requestAccess(for: .audio) { micOK in
                Task { @MainActor in
                    self.authorized = micOK
                    self.micDenied = !micOK
                    self.speechDenied = false
                    completion?(micOK)
                }
            }
            return
        }
        SFSpeechRecognizer.requestAuthorization { speechStatus in
            let speechOK = (speechStatus == .authorized)
            AVCaptureDevice.requestAccess(for: .audio) { micOK in
                Task { @MainActor in
                    self.authorized = speechOK && micOK
                    self.micDenied = (AVCaptureDevice.authorizationStatus(for: .audio) == .denied
                                      || AVCaptureDevice.authorizationStatus(for: .audio) == .restricted)
                    self.speechDenied = (SFSpeechRecognizer.authorizationStatus() == .denied
                                         || SFSpeechRecognizer.authorizationStatus() == .restricted)
                    if !self.authorized {
                        NSLog("[Vera voice] not authorized — speech:\(speechOK) mic:\(micOK)")
                    }
                    completion?(self.authorized)
                }
            }
        }
    }

    /// True only when both speech + mic are already granted (no prompt).
    var permissionsGranted: Bool {
        SFSpeechRecognizer.authorizationStatus() == .authorized
            && AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    /// When we bypass Apple Speech (local Whisper STT), listening only needs the
    /// MICROPHONE — not Speech Recognition. The always-on loop checks this.
    var micGranted: Bool {
        AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
    }

    /// Whether we can actually run a listening turn right now. With local Whisper
    /// we need the mic + a reachable brain; with Apple we need the recognizer up.
    var recognizerAvailable: Bool {
        if useLocalWhisper { return micGranted }
        return (recognizer?.isAvailable ?? false)
    }

    /// BYPASS Apple's SFSpeechRecognizer (flaky on free-team / side-loaded builds:
    /// mic grants but recognition silently returns nothing). Instead capture mic
    /// audio ourselves and transcribe with the on-device Whisper in the brain
    /// (POST /api/transcribe). On by default — it's the path that actually works.
    var useLocalWhisper = true
    private lazy var whisper: WhisperListener = {
        let w = WhisperListener()
        w.onLevel = { [weak self] lvl, bright in
            self?.level = lvl; self?.brightness = bright
        }
        w.onPartial = { [weak self] text in self?.transcript = text }
        w.onFinal = { [weak self] text in self?.whisperFinal(text) }
        return w
    }()

    /// A completed utterance from the local-Whisper path.
    private func whisperFinal(_ text: String) {
        isListening = false
        level = 0; brightness = 0
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        didDeliverFinal = false
        if clean.isEmpty { onListenEndedEmpty?() }
        else { didDeliverFinal = true; Chime.done.play(); onFinal?(clean) }
    }

    /// A published mirror of the permission state so SwiftUI re-renders the banner
    /// the moment access changes (TCC status itself isn't observable). Refreshed on
    /// launch, when the app becomes active, and after a permission request. Starts
    /// nil = "not yet checked" so the banner never flashes before we actually know.
    @Published var micDenied: Bool? = nil
    @Published var speechDenied: Bool? = nil

    /// Re-read the live TCC status. Called when the window appears / the app
    /// becomes active (e.g. returning from Settings). IMPORTANT: when the user has
    /// just granted access, the cached status can still read stale — so we only
    /// ever CLEAR the hint here (authorized → no banner), never RAISE it. The hint
    /// is raised solely by a real failed mic tap (permissionNeeded), so it can't
    /// show "off" while the switch is on.
    func refreshPermissionState() {
        let mic = AVCaptureDevice.authorizationStatus(for: .audio)
        // LOCAL WHISPER: listening needs ONLY the mic — never read SFSpeech state
        // (and never require it), so the banner can't demand a Speech grant we no
        // longer use. Apple-Speech state is only consulted on the legacy path.
        let sp: SFSpeechRecognizerAuthorizationStatus = useLocalWhisper
            ? .authorized : SFSpeechRecognizer.authorizationStatus()
        DispatchQueue.main.async {
            self.micDenied = (mic == .denied || mic == .restricted)
            self.speechDenied = (sp == .denied || sp == .restricted)
            self.authorized = (mic == .authorized) && (self.useLocalWhisper || sp == .authorized)
            // becoming active after granting in Settings → drop the stale hint.
            if self.authorized { self.permissionNeeded = false }
        }
    }

    /// True only when something is ACTUALLY blocked (checked, not just un-asked).
    /// The banner reads this; it can't be a false positive because it's driven by
    /// refreshPermissionState() re-reading the live status.
    var permissionDenied: Bool { (micDenied == true) || (speechDenied == true) }

    /// Open the exact System Settings pane to grant the mic (or speech). Called
    /// ONLY when the user taps the optional "Open Settings" button — never
    /// automatically. Opened async so it can never block the app's UI.
    func openPrivacySettings(speech: Bool = false) {
        let key = speech ? "Privacy_SpeechRecognition" : "Privacy_Microphone"
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(key)") else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            NSWorkspace.shared.open(url)
        }
    }

    func toggleListening() {
        if isListening { stopListening() } else { startListening() }
    }

    /// Open the mic. `hunting` runs the same pipeline muted, purely watching
    /// for the user to speak over her (no UI state, no delivery) — the barge-in
    /// hunt that `speak`/`beginExternalSpeech` start.
    func startListening(hunting: Bool = false, over utterance: String = "") {
        // LOCAL WHISPER: the barge-in HUNT opened an SFSpeechRecognizer session
        // UNDER her voice — and merely touching Apple Speech on a free-team build
        // ABORTS the app under TCC ("crashed … without a usage description"), which
        // the always-on relaunch turned into a crash LOOP. With Whisper we simply
        // DON'T hunt: the always-on loop re-opens the mic after she finishes. So a
        // hunting request is a safe no-op here. (No Apple Speech is ever touched.)
        if useLocalWhisper && hunting { return }
        // LOCAL WHISPER PATH — a REAL listening turn, captured + transcribed locally.
        if useLocalWhisper && !hunting {
            // need the mic; if it's not granted, ask once (mic only — no speech).
            guard micGranted else {
                AVCaptureDevice.requestAccess(for: .audio) { [weak self] ok in
                    Task { @MainActor in
                        guard let self else { return }
                        if ok { self.startListening() }
                        else { self.permissionNeeded = true; self.isListening = false }
                    }
                }
                return
            }
            stopSpeaking()            // never listen over her own voice
            transcript = ""
            didDeliverFinal = false
            isListening = true
            permissionNeeded = false
            micUnavailable = false
            Chime.listen.play()
            whisper.start()
            return
        }
        // Permission gate: if speech + mic aren't both granted yet, request them
        // and — once granted — retry this exact call. This is what makes the mic
        // button WORK on first tap instead of silently failing (the old code
        // never requested mic access, so AVAudioEngine.start() threw and the
        // catch below returned quietly).
        // Simple: ONE user action grants it. Tapping the mic asks macOS for
        // permission; the user allows; we listen. We do NOT auto-open System
        // Settings here — that jump is what froze the app. If it's still not
        // granted, we just publish a gentle flag the UI can show with a plain
        // "Open Settings" button the USER can choose to tap. No forced jumps,
        // no spinning, no hang.
        if !permissionsGranted {
            requestPermission { [weak self] ok in
                guard let self else { return }
                self.isListening = false
                if ok {
                    self.startListening(hunting: hunting, over: utterance)
                } else {
                    // couldn't get the grant from the prompt — surface it calmly;
                    // the UI offers a button, the user decides.
                    self.permissionNeeded = true
                }
            }
            return
        }
        // Recognizer must actually be present + available on this machine. If it
        // isn't (no speech model, or the system recognizer is momentarily down),
        // DON'T start a tap that will instantly error and toggle the button back
        // off — "it loops back to unclick". Surface a clear, one-time state instead.
        guard let rec = recognizer, rec.isAvailable else {
            isListening = false
            micUnavailable = true
            NSLog("[Vera voice] speech recognizer unavailable — not starting mic")
            return
        }
        micUnavailable = false
        // A REAL turn (a deliberate tap) always wins the single mic. If a muted
        // session — the wake-word watch or a barge-in hunt — is holding it, the
        // `request == nil` guard below would silently swallow the tap ("the mic
        // button does nothing"). Tear that muted session down first so the tap
        // always opens a real turn.
        if !hunting && (muted || request != nil) {
            keepWatching = false   // a deliberate turn overrides the idle name-watch
            tearDownSession()
        }
        // never listen over our own voice; this also ends any barge hunt, so a
        // real turn can always begin
        if !hunting { stopSpeaking() }
        if hunting && muted && request != nil {
            // hunt already running for her previous utterance — refresh the
            // echo filter so her NEW words don't read as an interruption
            echoWords.formUnion(Self.wordSet(utterance))
            return
        }
        guard request == nil else { return }     // one session at a time
        muted = hunting
        echoWords = hunting ? Self.wordSet(utterance) : []
        displayFromSegment = 0
        didDeliverFinal = false                  // fresh turn
        // a hunt over her utterance is never a name watch (and vice versa)
        if !hunting || !utterance.isEmpty { nameWords = [] }
        sessionStart = Date()
        if !hunting {
            transcript = ""
            listenStart = Date()
            lastVoiceAt = Date()
            lastTranscriptLength = 0
            recognizerFailures = 0   // a deliberate turn always gets a fresh attempt
            Chime.listen.play()
        }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        // Prefer on-device recognition (private) — but ONLY when this machine
        // actually SUPPORTS it. Forcing it on when the on-device model isn't
        // available makes the recognizer silently return nothing: the mic records
        // but never transcribes ("mic exists but is bad"). Fall back to the system
        // recognizer so dictation always works; it's still local user audio.
        req.requiresOnDeviceRecognition = recognizer?.supportsOnDeviceRecognition ?? false
        request = req

        // Always rebind to the LIVE hardware. A stale cached input format (left
        // over after a route change while the engine was stopped) is the quiet
        // killer: start() throws, or the tap installs against the wrong format
        // and never delivers buffers. Stopping + resetting drops every cached
        // node state so the format we read next is the one the device is
        // actually running right now.
        engine.stop()
        engine.reset()
        let input = engine.inputNode
        input.removeTap(onBus: 0)
        // apply (or drop) voice isolation between sessions, never mid-flight
        if isolationApplied != isolateVoice {
            try? input.setVoiceProcessingEnabled(isolateVoice)
            isolationApplied = isolateVoice
        }
        // Read the live device format. Right after stop()+reset() the input node
        // often hasn't re-settled on the HAL yet, so inputFormat can momentarily
        // report 0 channels / 0 Hz — which previously made us bail and the mic
        // NEVER opened ("listen does nothing"). Prefer inputFormat, fall back to
        // outputFormat, and only give up if BOTH are unusable. Nudge the engine to
        // re-settle with prepare() and retry the read before bailing.
        func liveFormat() -> AVAudioFormat {
            let f = input.inputFormat(forBus: 0)
            if f.channelCount > 0 && f.sampleRate > 0 { return f }
            return input.outputFormat(forBus: 0)
        }
        var format = liveFormat()
        if format.channelCount == 0 || format.sampleRate == 0 {
            engine.prepare()                 // let the input node re-attach to the device
            format = liveFormat()
        }
        guard format.channelCount > 0, format.sampleRate > 0 else {
            NSLog("[Vera voice] no live input format yet — not starting mic")
            request = nil
            isListening = false
            micUnavailable = !hunting   // only tell the user when THEY asked
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            req.append(buffer)
            self?.updateLevel(from: buffer)
        }

        engine.prepare()
        do {
            try engine.start()
        } catch {
            // A failed start is exactly why "the mic button does nothing". One
            // reset+retry handles the common transient (the device renegotiated
            // between our reset and start); only after that do we surface it.
            NSLog("[Vera voice] AVAudioEngine.start() failed: \(error.localizedDescription) — retrying once")
            input.removeTap(onBus: 0)
            engine.reset()
            engine.prepare()
            let retryFormat = liveFormat()
            if retryFormat.channelCount > 0 {
                input.installTap(onBus: 0, bufferSize: 1024, format: retryFormat) { [weak self] buffer, _ in
                    req.append(buffer)
                    self?.updateLevel(from: buffer)
                }
            }
            do {
                try engine.start()
            } catch {
                NSLog("[Vera voice] AVAudioEngine.start() failed again: \(error.localizedDescription)")
                input.removeTap(onBus: 0)
                request = nil
                isListening = false
                micUnavailable = !hunting   // best UX: say it's unavailable, don't look idle
                return
            }
        }
        if !hunting { isListening = true }
        permissionNeeded = false   // the mic is working now — clear any stale hint
        micUnavailable = false

        task = recognizer?.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in
                    self.recognizerFailures = 0   // a real result → healthy again
                    self.ingest(result)
                }
            }
            if error != nil {
                Task { @MainActor in
                    if self.muted {
                        let names = Array(self.nameWords)
                        self.tearDownSession()
                        // A name watch survives recognizer HICCUPS — re-arm. But if
                        // the recognizer keeps erroring immediately (e.g. an ad-hoc
                        // app TCC issue, or no on-device model), re-arming instantly
                        // becomes a TIGHT ERROR LOOP that pins the CPU and the mic
                        // never works. Cap consecutive failures and back off so it
                        // can't loop; it recovers on the next successful result.
                        self.recognizerFailures += 1
                        if self.keepWatching && !names.isEmpty
                            && self.recognizerFailures < 3 {
                            let backoff = 0.4 * Double(self.recognizerFailures)
                            DispatchQueue.main.asyncAfter(deadline: .now() + backoff) {
                                self.startNameWatch(names)
                            }
                        } else if self.recognizerFailures >= 3 {
                            // give up the watch quietly — don't spin. The user can
                            // still tap the mic for a real turn, which resets this.
                            self.keepWatching = false
                            NSLog("[Vera voice] name-watch disabled after repeated recognizer errors")
                        }
                    } else {
                        self.recognizerFailures += 1
                        self.stopListening()
                    }
                }
            }
        }
    }

    /// Every partial lands here: live transcript + endpoint bookkeeping while
    /// listening; echo-filtered barge hunting while she speaks.
    private func ingest(_ result: SFSpeechRecognitionResult) {
        let segments = result.bestTranscription.segments
        if muted {
            // Name watch (idle): the ONLY trigger is her name — say it and a
            // real turn opens, transcript starting after the name itself.
            if !nameWords.isEmpty {
                for (i, seg) in segments.enumerated().reversed() {
                    let w = seg.substring.lowercased()
                        .trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
                    if nameWords.contains(w) {
                        bargeIn(fromSegment: i + 1)
                        return
                    }
                }
                return
            }
            // Hunting: her own words (and their echo through the mic) match the
            // utterance she's speaking — anything else is YOU. Mis-hearings of
            // her own voice happen, so the bar is: three non-echo words, or two
            // with real voice energy at the mic. A false trigger here steals
            // the user's turn — err toward letting her finish.
            let tail = Self.trailingUserRun(segments, echo: echoWords)
            if mediaNoisy {
                // A TV/music bed is playing: transcribed words alone are unreliable
                // (they might be the video, not you). Require real voice energy AT
                // the mic — someone speaking up close, over the bed — before we let
                // her be interrupted. This is what stops "the speaker cuts out while
                // I'm watching YouTube": the narrator can't barge in anymore.
                if tail.count >= 3 && level > 0.3 {
                    bargeIn(fromSegment: segments.count - tail.count)
                }
            } else if tail.count >= 3 || (tail.count >= 2 && level > 0.22) {
                bargeIn(fromSegment: segments.count - tail.count)
            }
            return
        }
        let text = Self.joined(segments, from: displayFromSegment)
        if text.count != lastTranscriptLength {
            lastTranscriptLength = text.count
            lastVoiceAt = Date()                 // words arriving = still talking
        }
        transcript = text
        if result.isFinal {
            let final = text
            stopListening(submit: false)         // stop quietly…
            deliverFinal(final)                  // …then deliver once
        }
    }

    /// The user spoke over her: cut the voice, keep the session, hide the echo
    /// prefix, and flip from hunting to a real listening turn — their first
    /// words are already in the transcript.
    private func bargeIn(fromSegment: Int) {
        muted = false
        displayFromSegment = fromSegment
        stopSpeaking(keepSession: true)
        isListening = true
        listenStart = Date()
        lastVoiceAt = Date()
        lastTranscriptLength = 0
        Chime.listen.play()
    }

    func stopListening(submit: Bool = true) {
        // local-Whisper turn: stop capture; submit flushes the buffered audio now.
        if useLocalWhisper && whisper.isCapturing {
            isListening = false
            level = 0; brightness = 0
            if submit { whisper.stopAndFlush() }   // transcribe what we have → onFinal
            else { whisper.cancel() }
            return
        }
        guard isListening || muted else { return }
        let wasListening = isListening
        tearDownSession()
        isListening = false
        muted = false
        level = 0
        brightness = 0
        if submit && wasListening {
            let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            deliverFinal(text)
        }
    }

    private func tearDownSession() {
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        request?.endAudio()
        task?.cancel()        // cancel (not finish) so no late isFinal re-fires
        request = nil
        task = nil
        muted = false
    }

    /// Deliver the final transcript to the app exactly once per listening turn.
    /// Fired when a REAL listening turn ends with no words (you stopped without
    /// saying anything). Always-on voice-mode uses this to re-open the mic instead
    /// of going dead — so she keeps listening until you turn voice-mode off.
    var onListenEndedEmpty: (() -> Void)?

    private func deliverFinal(_ text: String) {
        guard !didDeliverFinal else { return }
        didDeliverFinal = true
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !clean.isEmpty {
            Chime.done.play()
            onFinal?(clean)
        } else {
            onListenEndedEmpty?()   // nothing said → let the app re-arm (always-on)
        }
    }

    // ---- speaking ---------------------------------------------------------

    /// An override voice identifier (from settings); nil = auto-pick the warmest.
    var preferredVoiceID: String? {
        didSet { _chosenVoice = nil }   // re-resolve next time
    }
    private var _chosenVoice: AVSpeechSynthesisVoice?

    /// Pick the most natural available English voice: premium first, then
    /// enhanced, then a known-warm default — so Anita sounds human, not robotic.
    private func humaneVoice() -> AVSpeechSynthesisVoice? {
        if let id = preferredVoiceID, let v = AVSpeechSynthesisVoice(identifier: id) {
            return v
        }
        if let cached = _chosenVoice { return cached }

        let english = AVSpeechSynthesisVoice.speechVoices()
            .filter { $0.language.hasPrefix("en") }

        // Prefer higher audio quality, and warm female voices Apple ships as
        // premium/enhanced (Ava, Allison, Samantha, Zoe). Quality enum: default <
        // enhanced < premium.
        let warmNames = ["Ava", "Allison", "Samantha", "Zoe", "Serena", "Nora"]
        func score(_ v: AVSpeechSynthesisVoice) -> Int {
            var s = 0
            switch v.quality {
            case .premium: s += 100
            case .enhanced: s += 50
            default: break
            }
            if warmNames.contains(where: { v.name.contains($0) }) { s += 10 }
            if v.language == "en-US" { s += 2 }
            return s
        }
        let best = english.max { score($0) < score($1) }
        _chosenVoice = best ?? AVSpeechSynthesisVoice(language: "en-US")
        return _chosenVoice
    }

    func speak(_ text: String) {
        // Never stack utterances — stop anything in progress first.
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
        stopPiper()
        // Vera's own neural voice (soft female, Her-like) when available + enabled;
        // otherwise the system voice. Piper synthesis is remote (the brain), so it
        // runs async; the system fallback fires immediately if Piper can't.
        if piperEnabled && piperAvailable {
            speakWithPiper(text) { [weak self] ok in
                guard let self else { return }
                if !ok {
                    // neural failed → system voice; barge-in mic is safe there
                    self.speakWithSystem(text)
                    self.startListening(hunting: true, over: text)
                }
                // on success: do NOT open the mic — Kokoro plays through the
                // speakers and an open mic would hear her and loop ("talks to
                // herself"). Tap the mic to start a real turn.
            }
        } else {
            speakWithSystem(text)
            // the mic opens muted underneath her voice, hunting for interruption
            startListening(hunting: true, over: text)
        }
    }

    /// The system AVSpeechSynthesis path (fallback / when Piper is off).
    /// What she should SAY: strip emoji / pictographs so the system voice never
    /// reads an emoji by its name aloud ("smiling face with smiling eyes"). The
    /// server's Kokoro/Piper paths do the same — this covers the AVSpeech fallback.
    private func speakable(_ text: String) -> String {
        let cleaned = text.unicodeScalars.filter { s in
            !(s.properties.isEmoji && s.properties.isEmojiPresentation)
              && !s.properties.isEmojiModifier
              && !s.properties.isEmojiModifierBase
              && s != "\u{200D}" && s != "\u{FE0F}"
              && s.properties.generalCategory != .otherSymbol
        }
        return String(String.UnicodeScalarView(cleaned))
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func speakWithSystem(_ text: String) {
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
        let utter = AVSpeechUtterance(string: speakable(text))
        utter.voice = humaneVoice()
        utter.rate = 0.46
        utter.pitchMultiplier = 1.02
        utter.preUtteranceDelay = 0.05
        utter.postUtteranceDelay = 0.10
        synth.speak(utter)
    }

    /// Fetch a WAV from the brain's Piper endpoint and play it. `done(true)` on
    /// successful playback start; `done(false)` to trigger the system fallback.
    private func speakWithPiper(_ text: String, done: @escaping (Bool) -> Void) {
        guard let url = URL(string: "http://127.0.0.1:7878/api/voice/piper") else { done(false); return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text, "length_scale": 1.12])
        req.timeoutInterval = 120   // Kokoro cold synth can take a while; never time out into the robotic fallback
        URLSession.shared.dataTask(with: req) { [weak self] data, resp, _ in
            guard let self else { return }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200, let data, data.count > 44 else { DispatchQueue.main.async { done(false) }; return }
            DispatchQueue.main.async {
                do {
                    let player = try AVAudioPlayer(data: data)
                    player.volume = 1.0          // ensure it's audible
                    let del = PiperPlayerDelegate { [weak self] in self?.speakingChanged(false) }
                    player.delegate = del
                    self.piperDelegate = del
                    self.piperPlayer = player
                    player.prepareToPlay()
                    self.speakingChanged(true)   // light the orb like she's speaking
                    player.play()
                    done(true)
                } catch {
                    done(false)
                }
            }
        }.resume()
    }

    private func stopPiper() {
        piperPlayer?.stop()
        piperPlayer = nil
        piperQueue.removeAll()
        piperPlaying = false
    }

    // a barge-in (or tap-to-stop) empties the queue; any fragments still
    // arriving from the model's stream must then be dropped, not spoken late
    private var streamCancelled = false

    /// Speak one piece of a STREAMED reply. Sentences peel off the model's
    /// stream and queue here, so she starts the first sentence while the rest
    /// still forms — the wait collapses from the whole answer to one sentence.
    /// Each fragment also refreshes the barge-in echo filter, so her own
    /// still-arriving words never read as an interruption.
    func speakFragment(_ text: String, first: Bool) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        if first {
            streamCancelled = false
            if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
            stopPiper()
        } else if streamCancelled {
            return
        }
        // Use Vera's OWN neural voice (Kokoro) per sentence when it's on and ready —
        // the warm synth is ~0.3s, fast enough to speak fragment-by-fragment. Only
        // fall back to the system AVSpeech voice (which sounds robotic) when the
        // neural voice is off or unavailable. This was the "too robotic" bug: the
        // streaming path always used AVSpeech and never her real voice.
        if piperEnabled && piperAvailable {
            speakFragmentWithPiper(t, first: first)
            // NOTE: with the neural voice we do NOT open the barge-in mic. Kokoro
            // plays through the SPEAKERS, so an open mic hears her own voice and
            // she ends up "talking to herself" (the echo filter keys on text, not
            // acoustics, so it can't reliably tell her audio from yours). Barge-in
            // is a nice-to-have; not looping on herself is essential. The user can
            // always tap the mic to start a real turn, which stops her first.
        } else {
            speakFragmentWithSystem(t, first: first)
            // AVSpeech routes differently + the echo filter was tuned for it, so
            // the barge-in hunt is safe here.
            startListening(hunting: true, over: t)
        }
    }

    /// One streamed fragment via the system AVSpeech voice (fallback path).
    private func speakFragmentWithSystem(_ t: String, first: Bool) {
        let utter = AVSpeechUtterance(string: speakable(t))
        utter.voice = humaneVoice()
        utter.rate = 0.46
        utter.pitchMultiplier = 1.02
        utter.preUtteranceDelay = first ? 0.05 : 0
        utter.postUtteranceDelay = 0.06
        synth.speak(utter)
    }

    /// One streamed fragment via Kokoro (her real voice). Fragments are queued so
    /// they play in order; a failure on any fragment degrades THAT fragment to the
    /// system voice rather than dropping her voice entirely.
    private func speakFragmentWithPiper(_ t: String, first: Bool) {
        guard let url = URL(string: "http://127.0.0.1:7878/api/voice/piper") else {
            speakFragmentWithSystem(t, first: first); return
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["text": t, "length_scale": 1.12])
        req.timeoutInterval = 120   // Kokoro cold synth can take a while; never time out into the robotic fallback
        URLSession.shared.dataTask(with: req) { [weak self] data, resp, _ in
            guard let self else { return }
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            let ok = (code == 200 && data != nil && (data?.count ?? 0) > 44)
            // Decide on the main actor (streamCancelled is main-actor state); never
            // read it from this background closure.
            DispatchQueue.main.async {
                guard !self.streamCancelled else { return }
                if ok, let data { self.enqueuePiper(data) }
                else { self.speakFragmentWithSystem(t, first: first) }
            }
        }.resume()
    }

    // Ordered playback queue for streamed Kokoro fragments, so sentences that
    // finish synthesizing out of order still play in the order they were spoken.
    private var piperQueue: [Data] = []
    private var piperPlaying = false

    private func enqueuePiper(_ data: Data) {
        piperQueue.append(data)
        if !piperPlaying { playNextPiper() }
    }

    private func playNextPiper() {
        guard !piperQueue.isEmpty, !streamCancelled else {
            piperPlaying = false
            if !synth.isSpeaking { speakingChanged(false) }
            return
        }
        piperPlaying = true
        let data = piperQueue.removeFirst()
        do {
            let player = try AVAudioPlayer(data: data)
            player.volume = 1.0            // ensure it's audible
            let del = PiperPlayerDelegate { [weak self] in
                DispatchQueue.main.async { self?.playNextPiper() }
            }
            player.delegate = del
            piperDelegate = del
            piperPlayer = player
            player.prepareToPlay()
            speakingChanged(true)
            player.play()
        } catch {
            // this fragment failed to play — skip to the next rather than stall
            playNextPiper()
        }
    }

    /// Start watching for her name (opt-in wake word). Muted, fully local,
    /// no posts anywhere. Safe to call every tick — it no-ops while any
    /// session is open or while she speaks.
    func startNameWatch(_ names: [String]) {
        guard request == nil, !isSpeaking else { return }
        let words = Set(names.map { $0.lowercased() }.filter { $0.count > 2 })
        guard !words.isEmpty else { return }
        nameWords = words
        keepWatching = true
        startListening(hunting: true)
    }

    func stopNameWatch() {
        keepWatching = false
        nameWords = []
        if muted && request != nil { tearDownSession() }
    }

    /// Cloned-voice playback happens server-side; the app still owns the
    /// speaking STATE — the orb, and the barge-in hunt over the same text.
    func beginExternalSpeech(_ text: String) {
        externalSpeech = true
        isSpeaking = true
        startListening(hunting: true, over: text)
    }

    func endExternalSpeech() {
        guard externalSpeech else { return }
        externalSpeech = false
        let was = isSpeaking
        isSpeaking = false
        if muted { tearDownSession() }           // the hunt ends with the voice
        if was { onSpeechEnded?() }              // hands-free: she's done → app may re-listen
    }

    // ---- streamed CLONED voice (her real voice, sentence-by-sentence) ----------
    // The cloned voice renders server-side; a whole-reply render meant ~15s of
    // silence before she spoke. We instead feed it one sentence at a time as the
    // reply streams, played strictly IN ORDER by a serial queue — so her real
    // voice starts after just the first sentence (~5s), and the rest follow
    // seamlessly. Barge-in clears the queue (see stopSpeaking / stopPiper).
    private var clonedQueue: [String] = []
    private var clonedSpeaking = false
    private var clonedCancelled = false

    func speakClonedFragment(_ text: String, agent: AgentClient, first: Bool) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        if first {
            clonedCancelled = false
            clonedQueue.removeAll()
        }
        if clonedCancelled { return }
        clonedQueue.append(t)
        externalSpeech = true           // her voice is carrying this turn
        isSpeaking = true
        if !clonedSpeaking { drainClonedQueue(agent: agent) }
    }

    private func drainClonedQueue(agent: AgentClient) {
        guard !clonedCancelled, !clonedQueue.isEmpty else {
            clonedSpeaking = false
            if clonedQueue.isEmpty { isSpeaking = synth.isSpeaking }
            return
        }
        clonedSpeaking = true
        let sentence = clonedQueue.removeFirst()
        Task { [weak self] in
            // server renders + plays this ONE sentence, returns when it finishes —
            // so the next dequeue plays right after, in order.
            let ok = await agent.speak(sentence)
            await MainActor.run {
                guard let self else { return }
                if !ok && !self.clonedCancelled {
                    // this sentence failed to render in her voice — say it in the
                    // system voice rather than dropping it, then continue the queue.
                    self.speakFragmentWithSystem(sentence, first: false)
                }
                self.drainClonedQueue(agent: agent)
            }
        }
    }

    /// Clear any queued cloned sentences (barge-in / new turn).
    private func stopClonedStream() {
        clonedCancelled = true
        clonedQueue.removeAll()
        clonedSpeaking = false
    }

    /// Synth started/stopped talking (per-utterance).
    /// Fired exactly once each time she FINISHES speaking (any voice path). The app
    /// uses this for hands-free mode: after she answers a spoken turn out loud, open
    /// the mic again so you can just keep talking — no tapping between turns.
    var onSpeechEnded: (() -> Void)?

    private func speakingChanged(_ speaking: Bool) {
        let was = isSpeaking
        isSpeaking = speaking || externalSpeech
        if !speaking && muted { tearDownSession() }   // she finished; hunt over
        // true speaking → not-speaking edge (and not just a barge mid-hunt): she's
        // done talking. Let the app decide whether to re-arm the mic (hands-free).
        if was && !isSpeaking { onSpeechEnded?() }
    }

    /// List installed English voices (for a settings picker), warmest first.
    func availableVoices() -> [(id: String, label: String)] {
        AVSpeechSynthesisVoice.speechVoices()
            .filter { $0.language.hasPrefix("en") }
            .sorted { a, b in
                if a.quality != b.quality { return a.quality.rawValue > b.quality.rawValue }
                return a.name < b.name
            }
            .map { v in
                let q = v.quality == .premium ? " ✦" : v.quality == .enhanced ? " ·" : ""
                return (v.identifier, "\(v.name) (\(v.language))\(q)")
            }
    }

    /// Stop talking immediately (tap-to-interrupt, like Siri).
    /// `keepSession = true` is the barge-in path: the mic session survives
    /// because it has already become the user's next turn.
    func stopSpeaking(keepSession: Bool = false) {
        streamCancelled = true      // late stream fragments must stay silent
        stopClonedStream()          // clear any queued cloned sentences
        if synth.isSpeaking || synth.isPaused {
            synth.stopSpeaking(at: .immediate)
        }
        stopPiper()                 // stop any neural-voice playback too
        if externalSpeech {
            externalSpeech = false
            // best-effort: tell the server to stop cloned playback
            if let url = URL(string: "http://127.0.0.1:7878/api/speak/stop") {
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                URLSession.shared.dataTask(with: req).resume()
            }
        }
        isSpeaking = false
        if !keepSession && muted { tearDownSession() }
    }

    /// One control to rule them all: if speaking, shut up; if listening, stop and
    /// submit; otherwise start listening. This is the Siri tap behaviour.
    func primaryTap() {
        if isSpeaking { stopSpeaking(); return }
        toggleListening()
    }

    // ---- signal extraction --------------------------------------------------

    /// RMS → level, zero-crossing rate → brightness, plus the endpoint check:
    /// once you've said something and gone quiet ~0.9 s, the turn submits itself.
    private func updateLevel(from buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength)
        var sum: Float = 0
        var crossings = 0
        var prev: Float = 0
        for i in 0..<n {
            let s = ch[i]
            sum += s * s
            if (s > 0) != (prev > 0) { crossings += 1 }
            prev = s
        }
        let rms = sqrt(sum / Float(max(1, n)))
        let scaled = min(1.0, CGFloat(rms) * 12)   // amplify quiet speech
        // ZCR: voiced vowels ~0.02–0.08, sibilants 0.2+; normalize to 0…1 and
        // gate by level so silence doesn't sparkle
        let zcr = CGFloat(crossings) / CGFloat(max(1, n))
        let sparkle = min(1.0, max(0, (zcr - 0.04) * 4)) * min(1, scaled * 3)
        Task { @MainActor in
            self.level = self.level * 0.7 + scaled * 0.3      // smoothing
            self.brightness = self.brightness * 0.6 + sparkle * 0.4
            if scaled > 0.16 { self.lastVoiceAt = Date() }
            // on-device recognition quietly stalls near a minute: recycle a
            // long-lived name watch before it goes deaf
            if self.muted && self.keepWatching && !self.nameWords.isEmpty
                && Date().timeIntervalSince(self.sessionStart) > 50 {
                let names = Array(self.nameWords)
                self.tearDownSession()
                self.startNameWatch(names)
            }
            self.checkEndpoint()
        }
    }

    private func checkEndpoint() {
        guard isListening, !muted else { return }
        let now = Date()
        if transcript.isEmpty {
            // nothing said at all: close quietly after 8 s rather than
            // listening into the room forever
            if now.timeIntervalSince(listenStart) > 8 { stopListening(submit: false) }
            return
        }
        // no turn lives forever: if recognition stalls mid-turn, submit what we
        // have at 45 s instead of trapping the mic (and the input field) open
        if now.timeIntervalSince(listenStart) > 45 { stopListening(submit: true); return }
        guard now.timeIntervalSince(listenStart) > endpointMinTurn,
              now.timeIntervalSince(lastVoiceAt) > endpointSilence else { return }
        stopListening(submit: true)
    }

    // ---- word tools (barge-in echo filter) -----------------------------------

    private static func wordSet(_ s: String) -> Set<String> {
        Set(s.lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { $0.count > 1 })
    }

    /// The run of segments at the tail that are NOT her words — the user's voice.
    private static func trailingUserRun(_ segments: [SFTranscriptionSegment],
                                        echo: Set<String>) -> [SFTranscriptionSegment] {
        var run: [SFTranscriptionSegment] = []
        for seg in segments.reversed() {
            let w = seg.substring.lowercased()
                .trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
            if w.count > 1 && !echo.contains(w) {
                run.insert(seg, at: 0)
            } else {
                break
            }
        }
        return run
    }

    private static func joined(_ segments: [SFTranscriptionSegment], from: Int) -> String {
        guard from < segments.count else { return "" }
        return segments[from...].map(\.substring).joined(separator: " ")
    }
}

/// Bridges AVSpeechSynthesizer callbacks: speaking state + per-word pulses.
private final class SpeechDelegate: NSObject, AVSpeechSynthesizerDelegate {
    let onChange: (Bool) -> Void
    let onWord: () -> Void
    init(onChange: @escaping (Bool) -> Void, onWord: @escaping () -> Void) {
        self.onChange = onChange
        self.onWord = onWord
    }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didStart u: AVSpeechUtterance) { onChange(true) }
    // report the QUEUE, not the utterance: a streamed reply is several queued
    // utterances that must read as one breath — no flicker between sentences
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { onChange(s.isSpeaking) }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { onChange(s.isSpeaking) }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, willSpeakRangeOfSpeechString r: NSRange,
                           utterance u: AVSpeechUtterance) { onWord() }
}

/// Bridges AVAudioPlayer's finish callback so the orb settles when Vera's neural
/// (Piper) voice stops speaking.
private final class PiperPlayerDelegate: NSObject, AVAudioPlayerDelegate {
    let onDone: () -> Void
    init(onDone: @escaping () -> Void) { self.onDone = onDone }
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        DispatchQueue.main.async { self.onDone() }
    }
}
