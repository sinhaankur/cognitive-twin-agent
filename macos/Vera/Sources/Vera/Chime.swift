import AVFoundation

/// Siri-grade sound design with zero assets: two soft sine dyads generated in
/// code. An upward pair when she starts listening ("I'm here"), a downward
/// pair when the turn ends ("got it"). Quiet on purpose — a cue, not a chime
/// concert. Rendered once into buffers, played through a tiny dedicated
/// engine so they never fight the mic engine or the synthesizer.
enum Chime {
    case listen   // E5 → A5, rising: your turn
    case done     // A5 → E5, settling: heard you

    private static let engine = AVAudioEngine()
    private static let player = AVAudioPlayerNode()
    private static var ready = false
    private static var buffers: [String: AVAudioPCMBuffer] = [:]

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

    /// Two notes, 90 ms each with a 25 ms crossfade; soft sine with a gentle
    /// attack/decay envelope so nothing clicks.
    private static func dyad(_ f0: Double, _ f1: Double) -> AVAudioPCMBuffer? {
        let dur = 0.21
        let n = Int(dur * sampleRate)
        guard let buf = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(n)),
              let ch = buf.floatChannelData?[0] else { return nil }
        buf.frameLength = AVAudioFrameCount(n)
        for i in 0..<n {
            let t = Double(i) / sampleRate
            // crossfade between the two notes at the midpoint
            let mix = min(1, max(0, (t - 0.085) / 0.05))
            let phase0 = 2 * .pi * f0 * t
            let phase1 = 2 * .pi * f1 * t
            let tone = sin(phase0) * (1 - mix) + sin(phase1) * mix
            // envelope: 12 ms attack, exponential release
            let attack = min(1, t / 0.012)
            let release = exp(-max(0, t - 0.12) * 22)
            ch[i] = Float(tone * attack * release * 0.9)
        }
        return buf
    }

    func play() {
        let (key, f0, f1): (String, Double, Double) = {
            switch self {
            case .listen: return ("listen", 659.26, 880.0)   // E5 → A5
            case .done:   return ("done",   880.0, 659.26)   // A5 → E5
            }
        }()
        guard Chime.ensureEngine() else { return }
        if Chime.buffers[key] == nil { Chime.buffers[key] = Chime.dyad(f0, f1) }
        guard let buf = Chime.buffers[key] else { return }
        Chime.player.stop()
        Chime.player.scheduleBuffer(buf, at: nil, options: .interrupts)
        Chime.player.play()
    }
}
