import AVFoundation

/// Her voice on the phone — entirely on-device.
///
/// On the Mac she speaks through the Kokoro neural voice served by the local
/// voice server; that server plays audio on the *Mac*, so it can't be her voice
/// on your phone. iOS already ships high-quality neural voices that run fully
/// on-device (nothing is sent anywhere), so on the phone she speaks through
/// AVSpeechSynthesizer. We pick the warmest female voice available and fall back
/// gracefully if a device has none installed.
///
/// Private by design: no audio leaves the phone, nothing is recorded, and she
/// only speaks replies you asked for.
@MainActor
final class Voice: NSObject, ObservableObject {
    static let shared = Voice()

    private let synth = AVSpeechSynthesizer()
    /// True while she's actually speaking — the orb can show a "speaking" state.
    @Published private(set) var speaking = false
    /// User preference: speak replies aloud. On by default — hearing her is the point.
    @Published var enabled: Bool = UserDefaults.standard.object(forKey: "voiceEnabled") as? Bool ?? true {
        didSet { UserDefaults.standard.set(enabled, forKey: "voiceEnabled") }
    }

    private override init() {
        super.init()
        synth.delegate = self
        #if os(iOS)
        // Let her voice mix gently with other audio and duck it, rather than
        // stopping the user's music outright.
        try? AVAudioSession.sharedInstance().setCategory(
            .playback, mode: .spokenAudio,
            options: [.duckOthers, .interruptSpokenAudioAndMixWithOthers]
        )
        #endif
    }

    /// The warmest on-device voice we can find. Prefers an enhanced/premium
    /// female en-US voice (Apple's neural "Siri"/enhanced voices), then any
    /// female en voice, then the system default. All on-device.
    private func bestVoice() -> AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices()
        // 1. premium or enhanced en-US female voices, highest quality first
        let ranked = voices
            .filter { $0.language.hasPrefix("en") }
            .sorted { lhs, rhs in lhs.quality.rawValue > rhs.quality.rawValue }
        // a soft, warm female first name we favour if present (Samantha/Ava/Allison)
        let warmNames = ["Ava", "Allison", "Samantha", "Nicky", "Zoe", "Joelle"]
        for name in warmNames {
            if let v = ranked.first(where: { $0.name.contains(name) }) { return v }
        }
        if let anyEnhanced = ranked.first(where: { $0.quality != .default }) { return anyEnhanced }
        return ranked.first ?? AVSpeechSynthesisVoice(language: "en-US")
    }

    /// Speak a reply aloud. No-op when muted or empty.
    func speak(_ text: String) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard enabled, !t.isEmpty else { return }
        stop()  // one voice at a time — never overlap her with herself
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setActive(true)
        #endif
        let u = AVSpeechUtterance(string: t)
        u.voice = bestVoice()
        // A gentle, unhurried cadence — a mother's kind of presence, not a reader.
        u.rate = AVSpeechUtteranceDefaultSpeechRate * 0.94
        u.pitchMultiplier = 1.02
        u.postUtteranceDelay = 0.1
        synth.speak(u)
    }

    func stop() {
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
    }

    /// True if the phone actually has a usable voice installed.
    var hasVoice: Bool { bestVoice() != nil }
}

extension Voice: AVSpeechSynthesizerDelegate {
    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didStart u: AVSpeechUtterance) {
        Task { @MainActor in self.speaking = true }
    }
    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didFinish u: AVSpeechUtterance) {
        Task { @MainActor in self.speaking = false }
    }
    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer, didCancel u: AVSpeechUtterance) {
        Task { @MainActor in self.speaking = false }
    }
}
