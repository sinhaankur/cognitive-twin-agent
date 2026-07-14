import Foundation
import AVFoundation
import Speech

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

    // ---- endpointing state (main actor) ----
    private var listenStart = Date.distantPast
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

    /// Called when a final transcript is ready (user stopped talking).
    var onFinal: ((String) -> Void)?

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
    }

    func requestPermission() {
        SFSpeechRecognizer.requestAuthorization { status in
            Task { @MainActor in
                self.authorized = (status == .authorized)
            }
        }
    }

    func toggleListening() {
        if isListening { stopListening() } else { startListening() }
    }

    /// Open the mic. `hunting` runs the same pipeline muted, purely watching
    /// for the user to speak over her (no UI state, no delivery) — the barge-in
    /// hunt that `speak`/`beginExternalSpeech` start.
    func startListening(hunting: Bool = false, over utterance: String = "") {
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
        if !hunting {
            transcript = ""
            listenStart = Date()
            lastVoiceAt = Date()
            lastTranscriptLength = 0
            Chime.listen.play()
        }
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.requiresOnDeviceRecognition = true   // keep it local
        request = req

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            req.append(buffer)
            self?.updateLevel(from: buffer)
        }

        engine.prepare()
        do {
            try engine.start()
        } catch {
            request = nil
            return
        }
        if !hunting { isListening = true }

        task = recognizer?.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in self.ingest(result) }
            }
            if error != nil {
                Task { @MainActor in
                    if self.muted { self.tearDownSession() } else { self.stopListening() }
                }
            }
        }
    }

    /// Every partial lands here: live transcript + endpoint bookkeeping while
    /// listening; echo-filtered barge hunting while she speaks.
    private func ingest(_ result: SFSpeechRecognitionResult) {
        let segments = result.bestTranscription.segments
        if muted {
            // Hunting: her own words (and their echo through the mic) match the
            // utterance she's speaking — anything else is YOU. Mis-hearings of
            // her own voice happen, so the bar is: three non-echo words, or two
            // with real voice energy at the mic. A false trigger here steals
            // the user's turn — err toward letting her finish.
            let tail = Self.trailingUserRun(segments, echo: echoWords)
            if tail.count >= 3 || (tail.count >= 2 && level > 0.22) {
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
    private func deliverFinal(_ text: String) {
        guard !didDeliverFinal else { return }
        didDeliverFinal = true
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !clean.isEmpty {
            Chime.done.play()
            onFinal?(clean)
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
        let utter = AVSpeechUtterance(string: text)
        // Warmer, more human delivery: a touch slower than default, natural pitch,
        // gentle lead-in/out so it doesn't clip robotically.
        utter.voice = humaneVoice()
        utter.rate = 0.46
        utter.pitchMultiplier = 1.02
        utter.preUtteranceDelay = 0.05
        utter.postUtteranceDelay = 0.10
        synth.speak(utter)
        // the mic opens muted underneath her voice, hunting for interruption
        startListening(hunting: true, over: text)
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
        isSpeaking = false
        if muted { tearDownSession() }           // the hunt ends with the voice
    }

    /// Synth started/stopped talking (per-utterance).
    private func speakingChanged(_ speaking: Bool) {
        isSpeaking = speaking || externalSpeech
        if !speaking && muted { tearDownSession() }   // she finished; hunt over
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
        if synth.isSpeaking || synth.isPaused {
            synth.stopSpeaking(at: .immediate)
        }
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
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { onChange(false) }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { onChange(false) }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, willSpeakRangeOfSpeechString r: NSRange,
                           utterance u: AVSpeechUtterance) { onWord() }
}
