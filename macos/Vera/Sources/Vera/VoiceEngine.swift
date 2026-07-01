import Foundation
import AVFoundation
import Speech

/// Native, on-device voice: Apple's Speech framework for listening and
/// AVSpeechSynthesizer for talking back. No cloud, no extra dependencies.
///
/// Publishes:
///   transcript  the recognized text (updates live while you speak)
///   level       mic loudness 0…1 (drives the Siri wave amplitude)
///   isListening / isSpeaking  state for the UI
@MainActor
final class VoiceEngine: ObservableObject {
    @Published var transcript: String = ""
    @Published var level: CGFloat = 0          // 0…1 mic amplitude
    @Published var isListening = false
    @Published var isSpeaking = false
    @Published var authorized = false

    private let engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var didDeliverFinal = false   // guard: deliver onFinal once per turn
    private let synth = AVSpeechSynthesizer()
    // strong ref: AVSpeechSynthesizer.delegate is weak, so we must retain it or
    // the speaking-state callbacks (which light up the orb) never fire.
    private var speechDelegate: SpeechDelegate?

    /// Called when a final transcript is ready (user stopped talking).
    var onFinal: ((String) -> Void)?

    init() {
        let delegate = SpeechDelegate { [weak self] speaking in
            Task { @MainActor in self?.isSpeaking = speaking }
        }
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

    func startListening() {
        guard !isListening else { return }
        stopSpeaking()               // never listen over our own voice
        didDeliverFinal = false      // fresh turn
        transcript = ""
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
            return
        }
        isListening = true

        task = recognizer?.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                Task { @MainActor in self.transcript = result.bestTranscription.formattedString }
                if result.isFinal {
                    let text = result.bestTranscription.formattedString
                    Task { @MainActor in
                        self.stopListening(submit: false)   // stop quietly…
                        self.deliverFinal(text)             // …then deliver once
                    }
                }
            }
            if error != nil {
                Task { @MainActor in self.stopListening() }
            }
        }
    }

    func stopListening(submit: Bool = true) {
        guard isListening else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        request?.endAudio()
        task?.cancel()        // cancel (not finish) so no late isFinal re-fires
        request = nil
        task = nil
        isListening = false
        level = 0
        if submit {
            let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
            deliverFinal(text)
        }
    }

    /// Deliver the final transcript to the app exactly once per listening turn.
    private func deliverFinal(_ text: String) {
        guard !didDeliverFinal else { return }
        didDeliverFinal = true
        let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if !clean.isEmpty { onFinal?(clean) }
    }

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
    func stopSpeaking() {
        if synth.isSpeaking || synth.isPaused {
            synth.stopSpeaking(at: .immediate)
        }
        isSpeaking = false
    }

    /// One control to rule them all: if speaking, shut up; if listening, stop and
    /// submit; otherwise start listening. This is the Siri tap behaviour.
    func primaryTap() {
        if isSpeaking { stopSpeaking(); return }
        toggleListening()
    }

    /// RMS of the audio buffer → a smoothed 0…1 level for the wave.
    private func updateLevel(from buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength)
        var sum: Float = 0
        for i in 0..<n { sum += ch[i] * ch[i] }
        let rms = sqrt(sum / Float(max(1, n)))
        let scaled = min(1.0, CGFloat(rms) * 12)   // amplify quiet speech
        Task { @MainActor in
            self.level = self.level * 0.7 + scaled * 0.3  // smoothing
        }
    }
}

/// Bridges AVSpeechSynthesizer start/finish into a simple bool callback.
private final class SpeechDelegate: NSObject, AVSpeechSynthesizerDelegate {
    let onChange: (Bool) -> Void
    init(_ onChange: @escaping (Bool) -> Void) { self.onChange = onChange }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didStart u: AVSpeechUtterance) { onChange(true) }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) { onChange(false) }
    func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) { onChange(false) }
}
