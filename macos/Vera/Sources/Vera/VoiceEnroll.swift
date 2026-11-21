import AVFoundation
import SwiftUI

/// VoiceEnroll — teach Vera YOUR voice so she only responds to you.
///
/// Records a short clip of you reading a prompt, builds a 16 kHz mono WAV, and
/// sends it to the brain's /api/voice/enroll. The brain stores a small, sealed
/// voiceprint (numpy MFCC) — no audio is kept. After this, her hands-free listen
/// loop drops turns that aren't your voice (the TV, another person, her own echo).
///
/// Self-contained capture (its own AVAudioEngine) so it never tangles with the
/// live listening loop. Records a fixed window, with a live level for the UI.
@MainActor
final class VoiceEnroll: ObservableObject {
    enum Phase: Equatable { case idle, recording, sending, done(String), failed(String) }
    @Published var phase: Phase = .idle
    @Published var level: Double = 0          // 0…1 live mic level for the meter
    @Published var remaining: Double = 0      // seconds left in the recording

    private let engine = AVAudioEngine()
    private var samples: [Float] = []
    private var sampleRate: Double = 48_000
    private var timer: Timer?
    private let seconds: Double
    private let client: AgentClient

    init(seconds: Double = 6, client: AgentClient = AgentClient()) {
        self.seconds = seconds
        self.client = client
    }

    /// The line to read — long + varied enough to capture your timbre, short enough
    /// to feel easy. The words don't matter to the voiceprint; your voice does.
    static let prompt =
        "Hi, it's me. This is my voice — warm and steady, just the way I talk. "
        + "Remember it, so you always know it's me."

    func start() {
        guard phase != .recording else { return }
        samples.removeAll()
        level = 0
        remaining = seconds
        let input = engine.inputNode
        input.removeTap(onBus: 0)
        var fmt = input.inputFormat(forBus: 0)
        if fmt.channelCount == 0 || fmt.sampleRate == 0 {
            engine.prepare(); fmt = input.inputFormat(forBus: 0)
        }
        guard fmt.channelCount > 0, fmt.sampleRate > 0 else {
            phase = .failed("Couldn't open the microphone."); return
        }
        sampleRate = fmt.sampleRate
        input.installTap(onBus: 0, bufferSize: 2048, format: fmt) { [weak self] buffer, _ in
            self?.consume(buffer)
        }
        engine.prepare()
        do { try engine.start() } catch {
            phase = .failed("Microphone didn't start — allow it in Settings?"); return
        }
        phase = .recording
        timer?.invalidate()
        let t0 = Date()
        timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                self.remaining = max(0, self.seconds - Date().timeIntervalSince(t0))
                if self.remaining <= 0 { self.finish() }
            }
        }
    }

    func cancel() {
        stopEngine()
        timer?.invalidate()
        phase = .idle
    }

    private nonisolated func consume(_ buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength)
        var chunk = [Float](repeating: 0, count: n)
        var peak: Float = 0
        for i in 0..<n { chunk[i] = ch[i]; peak = max(peak, abs(ch[i])) }
        Task { @MainActor in
            self.samples.append(contentsOf: chunk)
            // smooth the level a touch so the meter isn't jumpy
            self.level = self.level * 0.6 + Double(min(1, peak * 3)) * 0.4
        }
    }

    private func finish() {
        timer?.invalidate()
        stopEngine()
        guard samples.count > Int(sampleRate * 1.0) else {   // need at least ~1s
            phase = .failed("That was too short — try again and read the line.")
            return
        }
        phase = .sending
        let wav = Self.wav16kMono(from: samples, sourceRate: sampleRate)
        Task { [weak self] in
            guard let self else { return }
            let msg = await self.client.enrollVoice(wav)
            await MainActor.run {
                self.phase = msg.lowercased().contains("couldn't") ? .failed(msg) : .done(msg)
            }
        }
    }

    private func stopEngine() {
        if engine.isRunning { engine.stop() }
        engine.inputNode.removeTap(onBus: 0)
    }

    // ── WAV build (16 kHz mono PCM16, linear resample) ─────────────────────────
    private nonisolated static func wav16kMono(from input: [Float], sourceRate: Double) -> Data {
        let target = 16_000.0
        let ratio = sourceRate / target
        let outCount = max(0, Int(Double(input.count) / ratio))
        var pcm = [Int16](repeating: 0, count: outCount)
        for i in 0..<outCount {
            let pos = Double(i) * ratio
            let idx = Int(pos)
            let frac = Float(pos - Double(idx))
            let a = idx < input.count ? input[idx] : 0
            let b = (idx + 1) < input.count ? input[idx + 1] : a
            let s = max(-1, min(1, a + (b - a) * frac))
            pcm[i] = Int16(s * 32767)
        }
        let sr = Int(target), dataSize = pcm.count * 2
        var d = Data()
        func str(_ s: String) { d.append(s.data(using: .ascii)!) }
        func u32(_ v: UInt32) { var x = v.littleEndian; withUnsafeBytes(of: &x) { d.append(contentsOf: $0) } }
        func u16(_ v: UInt16) { var x = v.littleEndian; withUnsafeBytes(of: &x) { d.append(contentsOf: $0) } }
        str("RIFF"); u32(UInt32(36 + dataSize)); str("WAVE")
        str("fmt "); u32(16); u16(1); u16(1)
        u32(UInt32(sr)); u32(UInt32(sr * 2)); u16(2); u16(16)
        str("data"); u32(UInt32(dataSize))
        pcm.withUnsafeBytes { d.append(contentsOf: $0) }
        return d
    }
}

// ── The enroll window ─────────────────────────────────────────────────────────
struct VoiceEnrollView: View {
    @StateObject private var rec = VoiceEnroll()

    var body: some View {
        VStack(spacing: 18) {
            Text("Teach me your voice")
                .font(.system(size: 18, weight: .semibold))
            Text("So I learn you — not the TV, not another person, not my own voice. "
                 + "Read this out loud, naturally. I'll keep getting surer every time "
                 + "we talk:")
                .font(.system(size: 12.5))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)

            Text("“" + VoiceEnroll.prompt + "”")
                .font(.system(size: 15, design: .serif))
                .italic()
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
                .padding(.vertical, 6)

            // live meter while recording
            if rec.phase == .recording {
                HStack(spacing: 10) {
                    Image(systemName: "mic.fill").foregroundStyle(Color.accentColor)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.primary.opacity(0.1))
                            Capsule().fill(Color.accentColor)
                                .frame(width: geo.size.width * rec.level)
                        }
                    }.frame(height: 6)
                    Text("\(Int(ceil(rec.remaining)))s").font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(.secondary)
                }.frame(width: 320, height: 20)
            }

            statusLine

            controls
        }
        .padding(28)
        .frame(width: 440)
    }

    @ViewBuilder private var statusLine: some View {
        switch rec.phase {
        case .sending: Label("Learning your voice…", systemImage: "waveform")
            .font(.system(size: 12)).foregroundStyle(.secondary)
        case .done(let m): Label(m, systemImage: "checkmark.circle.fill")
            .font(.system(size: 12)).foregroundStyle(Color.accentColor).frame(maxWidth: 360)
        case .failed(let m): Label(m, systemImage: "exclamationmark.triangle")
            .font(.system(size: 12)).foregroundStyle(.orange).frame(maxWidth: 360)
        default: EmptyView()
        }
    }

    @ViewBuilder private var controls: some View {
        switch rec.phase {
        case .idle, .failed:
            Button { rec.start() } label: {
                Label("Start — read the line", systemImage: "mic.fill").frame(width: 220)
            }.buttonStyle(.borderedProminent).controlSize(.large)
        case .recording:
            Button(role: .cancel) { rec.cancel() } label: { Text("Stop").frame(width: 120) }
                .controlSize(.large)
        case .sending:
            ProgressView().controlSize(.small)
        case .done:
            VStack(spacing: 8) {
                Text("Say it once more to make it stronger (optional).")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                Button { rec.phase = .idle } label: { Text("Record again").frame(width: 160) }
                    .controlSize(.large)
            }
        }
    }
}
