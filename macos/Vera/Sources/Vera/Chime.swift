import AVFoundation

/// Siri-grade sound design with zero assets — a small, COHESIVE family of soft
/// tones generated in code. One voice, one character: gentle sine dyads, quiet
/// on purpose (a cue, not a chime concert), shaped so nothing ever clicks or
/// startles. Rendered once into buffers, played through a tiny dedicated engine
/// so they never fight the mic engine or the synthesizer.
///
/// Grounded in earcon convention (Blattner; Android/Material sound guidance):
///   • rising, consonant interval  = positive  (your turn / heard you / sent)
///   • falling / dissonant interval = error    (didn't catch that)
///   • energy sits in the ~500 Hz–2.6 kHz range the ear reads most clearly,
///     with soft attack + exponential release (no sharp transients → no fatigue)
///   • every cue is brief, low-level, and spaced — polite, repeat-friendly.
enum Chime {
    case listen   // E5 → A5, rising: your turn (I'm here)
    case done     // A5 → E5, settling: heard you
    case notify   // soft two-note lift: she has something for you (nudge/calendar)
    case error    // low, gentle fall: didn't catch that / failed (never harsh)
    case send     // a faint single tick: your message went
    case sent     // a soft confirm when her reply lands

    private static let engine = AVAudioEngine()
    private static let player = AVAudioPlayerNode()
    private static var ready = false
    private static var buffers: [String: AVAudioPCMBuffer] = [:]

    /// The master switch for ALL sound cues (listen/done/notify/send/sent — error
    /// is covered too). OFF by default: the cues were more annoying than helpful,
    /// so silence is the default and you opt IN from the menu (Voice & look ▸
    /// "Sound cues"). Persisted; `nil` → default off.
    static var cuesEnabled: Bool {
        UserDefaults.standard.object(forKey: "vera.soundCues") as? Bool ?? false
    }
    static func setCuesEnabled(_ on: Bool) {
        UserDefaults.standard.set(on, forKey: "vera.soundCues")
    }

    private static func ensureEngine() -> Bool {
        if ready { return true }
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
        engine.mainMixerNode.outputVolume = 0.14        // felt, not heard
        do { try engine.start() } catch { return false }
        ready = true
        return true
    }

    private static let sampleRate = 44_100.0
    private static var format: AVAudioFormat {
        AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
    }

    // MARK: - Tone recipes
    //
    // Each cue is one or two soft notes. `gain` keeps the whole family at an even,
    // close intensity (earcon rule: don't let one cue jump out louder than the
    // rest). Single-note cues pass the same frequency twice.
    private struct Recipe {
        let key: String
        let f0: Double
        let f1: Double
        let dur: Double      // total length
        let gain: Double     // per-cue level, so the set stays even
    }

    private var recipe: Recipe {
        switch self {
        // rising consonant MAJOR THIRD = a soft, polite "I'm here" — a gentle
        // lower-register lift, not the old wide/bright fourth that read as "strange".
        case .listen: return Recipe(key: "listen", f0: 440.00, f1: 554.37, dur: 0.20, gain: 0.75) // A4→C#5
        case .done:   return Recipe(key: "done",   f0: 554.37, f1: 440.00, dur: 0.20, gain: 0.70) // C#5→A4 settle
        // a gentle lift a step up from listen, for "she has something for you"
        case .notify: return Recipe(key: "notify", f0: 493.88, f1: 659.26, dur: 0.26, gain: 0.72) // B4→E5
        // low, soft fall — present but never a harsh buzzer
        case .error:  return Recipe(key: "error",  f0: 440.00, f1: 392.00, dur: 0.24, gain: 0.55) // A4→G4
        // a faint single tick on send, and a soft single confirm when a reply lands
        case .send:   return Recipe(key: "send",   f0: 587.33, f1: 587.33, dur: 0.10, gain: 0.40) // D5 tick
        case .sent:   return Recipe(key: "sent",   f0: 659.26, f1: 659.26, dur: 0.14, gain: 0.48) // E5 confirm
        }
    }

    /// One soft tone (or a crossfaded dyad). Gentle attack + exponential release
    /// so it never clicks; a light 2nd-harmonic adds warmth without brightness.
    private static func render(_ r: Recipe) -> AVAudioPCMBuffer? {
        let n = Int(r.dur * sampleRate)
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(n)),
              let ch = buf.floatChannelData?[0] else { return nil }
        buf.frameLength = AVAudioFrameCount(n)
        let isDyad = abs(r.f0 - r.f1) > 0.5
        // crossfade window centred past the first note for a two-note cue
        let xStart = r.dur * 0.40, xLen = r.dur * 0.24
        for i in 0..<n {
            let t = Double(i) / sampleRate
            let sample: Double
            if isDyad {
                let mix = min(1, max(0, (t - xStart) / xLen))
                let a = softSine(r.f0, t)
                let b = softSine(r.f1, t)
                sample = a * (1 - mix) + b * mix
            } else {
                sample = softSine(r.f0, t)
            }
            // envelope: 12 ms attack, exponential release toward the tail
            let attack = min(1, t / 0.012)
            let release = exp(-max(0, t - r.dur * 0.55) * 20)
            ch[i] = Float(sample * attack * release * r.gain)
        }
        return buf
    }

    /// A warm sine: fundamental + a quiet 2nd harmonic (−12 dB). Soft, not pure
    /// and thin, but still polite (no high-frequency edge to fatigue the ear).
    private static func softSine(_ f: Double, _ t: Double) -> Double {
        let p = 2 * .pi * f * t
        return sin(p) + 0.25 * sin(2 * p)
    }

    func play() {
        // Opt-in: stay silent unless the user turned sound cues on.
        guard Chime.cuesEnabled else { return }
        let r = recipe
        guard Chime.ensureEngine() else { return }
        if Chime.buffers[r.key] == nil { Chime.buffers[r.key] = Chime.render(r) }
        guard let buf = Chime.buffers[r.key] else { return }
        // Don't cut off a cue mid-play with the next one unless it's the same slot;
        // scheduling with .interrupts keeps latency-masking cues snappy.
        Chime.player.scheduleBuffer(buf, at: nil, options: .interrupts)
        Chime.player.play()
    }
}

/// A near-silent ambient bed — a sense of "alive in the room" while she's
/// present. OFF by default and strictly opt-in (CTWIN/UserDefaults gate lives at
/// the call site); a slow, barely-there two-note pad with gentle amplitude drift,
/// so it never becomes a drone you notice. Same no-assets, pure-synth approach as
/// the cues, on its own quiet player so it can fade in/out independently.
final class AmbientBed {
    static let shared = AmbientBed()

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private var started = false
    private var fadeTimer: Timer?

    private let sampleRate = 44_100.0
    private var format: AVAudioFormat { AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)! }

    /// Begin the bed (idempotent). Fades up gently to a whisper level.
    func start() {
        guard !started else { return }
        guard let buf = renderLoop() else { return }
        engine.attach(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
        engine.mainMixerNode.outputVolume = 0.0
        do { try engine.start() } catch { return }
        player.scheduleBuffer(buf, at: nil, options: .loops)
        player.play()
        started = true
        fade(to: 0.05, over: 2.0)      // a whisper — felt, not heard
    }

    /// Fade out and stop — leaves no residual engine running.
    func stop() {
        guard started else { return }
        fade(to: 0.0, over: 1.2) { [weak self] in
            guard let self else { return }
            self.player.stop()
            self.engine.stop()
            self.started = false
        }
    }

    // A seamless ~8 s loop: two very close low notes beating slowly, with a slow
    // amplitude swell — deliberately plain so it reads as "air", not music.
    private func renderLoop() -> AVAudioPCMBuffer? {
        let dur = 8.0
        let n = Int(dur * sampleRate)
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(n)),
              let ch = buf.floatChannelData?[0] else { return nil }
        buf.frameLength = AVAudioFrameCount(n)
        let f0 = 110.0, f1 = 110.9       // a slow ~0.9 Hz beat
        for i in 0..<n {
            let t = Double(i) / sampleRate
            // loop-safe swell: a full cosine over the buffer so start==end
            let swell = 0.5 + 0.5 * cos(2 * .pi * (t / dur))
            let tone = sin(2 * .pi * f0 * t) + sin(2 * .pi * f1 * t)
            ch[i] = Float(tone * 0.5 * (0.5 + 0.5 * swell) * 0.4)
        }
        return buf
    }

    private func fade(to target: Float, over seconds: Double, then done: (() -> Void)? = nil) {
        fadeTimer?.invalidate()
        let steps = 30
        let dt = seconds / Double(steps)
        let start = engine.mainMixerNode.outputVolume
        var k = 0
        fadeTimer = Timer.scheduledTimer(withTimeInterval: dt, repeats: true) { [weak self] tm in
            guard let self else { tm.invalidate(); return }
            k += 1
            let p = Float(k) / Float(steps)
            self.engine.mainMixerNode.outputVolume = start + (target - start) * p
            if k >= steps { tm.invalidate(); done?() }
        }
    }
}
