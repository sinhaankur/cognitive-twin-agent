import Foundation
import AVFoundation

/// Captures microphone audio and transcribes it with the on-device Whisper running
/// in the brain (POST /api/transcribe) — a deliberate BYPASS of Apple's
/// SFSpeechRecognizer, which on free-team / side-loaded builds authorizes the mic
/// yet silently returns no transcription ("mic is on but it doesn't work").
///
/// Only the MICROPHONE permission is needed (it works). We never touch the Speech
/// Recognition entitlement. Everything stays on this machine: audio → local
/// Whisper → text, nothing leaves the box.
///
/// Endpointing is automatic (silence-detected): we watch the mic level, mark the
/// start of speech when it crosses a threshold, and end the turn after ~0.9s of
/// trailing silence — then flush the buffered audio to Whisper and emit `onFinal`.
@MainActor
final class WhisperListener {
    /// Live mic level (0…1) and spectral brightness (0…1) for the orb.
    var onLevel: ((CGFloat, CGFloat) -> Void)?
    /// A cheap interim hint shown while capturing (we don't have real partials from
    /// a batch STT, so this stays a gentle "listening…" placeholder the UI can use).
    var onPartial: ((String) -> Void)?
    /// The finished utterance (may be empty if nothing intelligible was said).
    var onFinal: ((String) -> Void)?

    private let engine = AVAudioEngine()
    private(set) var isCapturing = false

    // Accumulated mono float samples at the input's native rate.
    private var samples: [Float] = []
    private var inputSampleRate: Double = 48_000

    // ---- endpointing ----
    private var hasSpoken = false            // have we heard real speech yet this turn?
    private var lastLoudAt = Date()          // last time level crossed the speech gate
    private var turnStart = Date()
    private let speechGate: Float = 0.02     // RMS above this = voice present
    private let endSilence: TimeInterval = 0.9   // trailing silence that ends a turn (snappy)
    // LET YOU FINISH: the turn ends when you actually PAUSE (endSilence), not on a
    // clock. The cap is only a safety net for a stuck-open mic, so it's generous —
    // a long continuous thought survives whole instead of being chopped at 20s.
    private let maxTurn: TimeInterval = 90.0
    private let preSpeechTimeout: TimeInterval = 12.0  // give up if nothing is ever said
    private var endpointTimer: Timer?

    private let baseURL = URL(string: "http://127.0.0.1:7878")!

    // ---- barge-in monitor (listen UNDER her voice, no Apple Speech) ----
    /// Fires the instant the user speaks OVER her — so she can stop at once and
    /// listen. A separate, tiny RMS-only tap (no transcription, no Apple Speech,
    /// so it's crash-safe on free-team builds, unlike the old SFSpeech hunt).
    var onBarge: (() -> Void)?
    private let bargeEngine = AVAudioEngine()
    private var bargeMonitoring = false
    private var bargeLoudFrames = 0            // consecutive loud frames → real speech
    private var bargeStart = Date()
    private var bargeFloor: Float = 0.02       // learned ambient+her-bleed floor
    private var bargeFloorSamples = 0
    // SMART + FAST barge detection, self-calibrating so it doesn't false-trip on
    // her own voice bleeding into the mic or steady room noise:
    //   • GRACE: ignore the first ~350ms, while her audio first reaches the mic;
    //   • FLOOR: learn the ambient/bleed level over the next ~250ms, then require
    //     you to be clearly ABOVE it (×2.2) — so only YOU, louder than her bleed,
    //     trips it, on any device/volume;
    //   • CONSECUTIVE frames: a few in a row (~60ms) = real speech, not a blip.
    private let bargeGraceSec: TimeInterval = 0.35
    private let bargeCalibrateSec: TimeInterval = 0.25
    private let bargeOverFloor: Float = 2.2
    private let bargeAbsMin: Float = 0.03      // never trip on a whisper-quiet room
    private let bargeFramesToTrip = 3

    /// Begin a listening turn: open the mic and watch for speech → silence.
    func start() {
        if isCapturing { return }
        samples.removeAll(keepingCapacity: true)
        hasSpoken = false
        turnStart = Date()
        lastLoudAt = Date()

        // Always read the LIVE input format (a reset drops stale cached state after
        // a route change). Fall back to outputFormat if inputFormat hasn't settled.
        engine.stop()
        engine.reset()
        let input = engine.inputNode
        input.removeTap(onBus: 0)
        var fmt = input.inputFormat(forBus: 0)
        if fmt.channelCount == 0 || fmt.sampleRate == 0 {
            engine.prepare()
            fmt = input.inputFormat(forBus: 0)
        }
        if fmt.channelCount == 0 || fmt.sampleRate == 0 {
            fmt = input.outputFormat(forBus: 0)
        }
        guard fmt.channelCount > 0, fmt.sampleRate > 0 else {
            NSLog("[Vera whisper] no live input format — mic not started")
            onFinal?("")
            return
        }
        inputSampleRate = fmt.sampleRate

        input.installTap(onBus: 0, bufferSize: 2048, format: fmt) { [weak self] buffer, _ in
            self?.consume(buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            NSLog("[Vera whisper] engine.start failed: \(error.localizedDescription)")
            input.removeTap(onBus: 0)
            onFinal?("")
            return
        }
        isCapturing = true
        onPartial?("listening…")

        // Drive endpointing on the main actor (the tap runs on an audio thread).
        endpointTimer?.invalidate()
        endpointTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick() }
        }
    }

    /// Start watching for the user to speak OVER her, while she's talking. RMS only
    /// — no transcription, no Apple Speech — so it's crash-safe and SUPER FAST: a
    /// few loud frames (~60ms) trips `onBarge`, which the voice engine uses to stop
    /// her at once and open a real listening turn. Call when she begins speaking;
    /// `stopBargeMonitor()` when she stops.
    func startBargeMonitor() {
        if bargeMonitoring { return }
        bargeLoudFrames = 0
        bargeStart = Date()
        bargeFloor = bargeAbsMin
        bargeFloorSamples = 0
        let input = bargeEngine.inputNode
        input.removeTap(onBus: 0)
        var fmt = input.inputFormat(forBus: 0)
        if fmt.channelCount == 0 || fmt.sampleRate == 0 { bargeEngine.prepare(); fmt = input.inputFormat(forBus: 0) }
        guard fmt.channelCount > 0, fmt.sampleRate > 0 else { return }
        input.installTap(onBus: 0, bufferSize: 1024, format: fmt) { [weak self] buffer, _ in
            self?.bargeInspect(buffer)
        }
        bargeEngine.prepare()
        do { try bargeEngine.start() } catch { return }
        bargeMonitoring = true
    }

    func stopBargeMonitor() {
        guard bargeMonitoring else { return }
        bargeEngine.inputNode.removeTap(onBus: 0)
        bargeEngine.stop()
        bargeMonitoring = false
        bargeLoudFrames = 0
    }

    private nonisolated func bargeInspect(_ buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength); if n == 0 { return }
        var sum: Float = 0
        for i in 0..<n { let s = ch[i]; sum += s * s }
        let rms = sqrt(sum / Float(n))
        Task { @MainActor [weak self] in self?.bargeConsider(rms: rms) }
    }

    private func bargeConsider(rms: Float) {
        guard bargeMonitoring else { return }
        let elapsed = Date().timeIntervalSince(bargeStart)
        // 1) GRACE — her audio is just reaching the mic; ignore it entirely.
        if elapsed < bargeGraceSec { return }
        // 2) CALIBRATE — learn the ambient + her-bleed floor (rolling max-ish mean).
        if elapsed < bargeGraceSec + bargeCalibrateSec {
            bargeFloorSamples += 1
            bargeFloor = max(bargeFloor, rms)   // the loudest steady bleed = the floor
            return
        }
        // 3) DETECT — you must be clearly ABOVE her bleed AND a sane absolute min.
        let threshold = max(bargeAbsMin, bargeFloor * bargeOverFloor)
        if rms >= threshold {
            bargeLoudFrames += 1
            if bargeLoudFrames >= bargeFramesToTrip {
                stopBargeMonitor()
                onBarge?()          // → voice engine: stop speaking, listen NOW
            }
        } else {
            bargeLoudFrames = 0     // require CONSECUTIVE loud frames (real speech, not a blip)
        }
    }

    /// Stop capturing and transcribe whatever we have (the user tapped stop, or the
    /// app is submitting the turn now).
    func stopAndFlush() {
        guard isCapturing else { return }
        teardown()
        flush()
    }

    /// Stop capturing and DISCARD the audio (voice-mode off / cancelled).
    func cancel() {
        guard isCapturing else { onFinal?(""); return }
        teardown()
        samples.removeAll()
        onFinal?("")
    }

    // ---- capture ----

    private nonisolated func consume(_ buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength)
        if n == 0 { return }
        var sum: Float = 0
        var crossings = 0
        var prev: Float = 0
        var chunk = [Float](repeating: 0, count: n)
        for i in 0..<n {
            let s = ch[i]
            chunk[i] = s
            sum += s * s
            if (s > 0) != (prev > 0) { crossings += 1 }
            prev = s
        }
        let rms = sqrt(sum / Float(n))
        let level = min(1.0, CGFloat(rms) * 12)
        let zcr = CGFloat(crossings) / CGFloat(n)
        let bright = min(1.0, max(0, (zcr - 0.04) * 4)) * min(1, level * 3)
        Task { @MainActor [weak self] in
            self?.append(chunk, rms: rms, level: level, bright: bright)
        }
    }

    private func append(_ chunk: [Float], rms: Float, level: CGFloat, bright: CGFloat) {
        guard isCapturing else { return }
        samples.append(contentsOf: chunk)
        onLevel?(level, bright)
        if rms > speechGate {
            lastLoudAt = Date()
            if !hasSpoken { hasSpoken = true }
        }
    }

    // ---- endpointing ----

    private func tick() {
        guard isCapturing else { return }
        let now = Date()
        // hard cap
        if now.timeIntervalSince(turnStart) > maxTurn { stopAndFlush(); return }
        if !hasSpoken {
            // nothing said yet — give up after a while so we don't hold the mic open
            // forever on a silent room (the always-on loop will re-arm).
            if now.timeIntervalSince(turnStart) > preSpeechTimeout {
                teardown(); samples.removeAll(); onFinal?("")
            }
            return
        }
        // speech heard → end the turn once the trailing silence is long enough.
        if now.timeIntervalSince(lastLoudAt) > endSilence {
            stopAndFlush()
        }
    }

    private func teardown() {
        endpointTimer?.invalidate(); endpointTimer = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        isCapturing = false
        onLevel?(0, 0)
    }

    // ---- transcription ----

    private func flush() {
        let captured = samples
        samples.removeAll()
        // too short to be speech → empty turn
        guard captured.count > Int(inputSampleRate * 0.25) else { onFinal?(""); return }
        let wav = Self.wav16kMono(from: captured, sourceRate: inputSampleRate)
        Task { [weak self] in
            let text = await self?.transcribe(wav) ?? ""
            await MainActor.run { self?.onFinal?(text) }
        }
    }

    private func transcribe(_ wav: Data) async -> String {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/transcribe"))
        req.httpMethod = "POST"
        req.setValue("audio/wav", forHTTPHeaderField: "Content-Type")
        req.httpBody = wav
        req.timeoutInterval = 30
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            // The server now returns the heard text even for noise words, with a
            // `heard` flag telling us whether to ACT on it. Only act on real
            // speech (heard == true); a stray "you"/"thank you" mishearing has
            // heard == false → treat as an empty turn (no command), so she doesn't
            // answer phantoms. The display cue for "didn't catch that" is handled
            // in whisperFinal.
            let heard = (obj["heard"] as? Bool) ?? true
            guard heard else { return "" }
            return (obj["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        } catch {
            NSLog("[Vera whisper] transcribe failed: \(error.localizedDescription)")
            return ""
        }
    }

    // ---- WAV encoding (linear resample to 16 kHz mono PCM16) ----

    private nonisolated static func wav16kMono(from input: [Float], sourceRate: Double) -> Data {
        let targetRate = 16_000.0
        let ratio = sourceRate / targetRate
        let outCount = Int(Double(input.count) / ratio)
        var pcm = [Int16](repeating: 0, count: max(0, outCount))
        var i = 0
        while i < outCount {
            let srcPos = Double(i) * ratio
            let idx = Int(srcPos)
            let frac = Float(srcPos - Double(idx))
            let a = idx < input.count ? input[idx] : 0
            let b = (idx + 1) < input.count ? input[idx + 1] : a
            var s = a + (b - a) * frac            // linear interpolation
            s = max(-1, min(1, s))
            pcm[i] = Int16(s * 32767)
            i += 1
        }
        return wavData(pcm16: pcm, sampleRate: Int(targetRate))
    }

    private nonisolated static func wavData(pcm16: [Int16], sampleRate: Int) -> Data {
        let byteRate = sampleRate * 2
        let dataSize = pcm16.count * 2
        var d = Data()
        func str(_ s: String) { d.append(s.data(using: .ascii)!) }
        func u32(_ v: UInt32) { var x = v.littleEndian; withUnsafeBytes(of: &x) { d.append(contentsOf: $0) } }
        func u16(_ v: UInt16) { var x = v.littleEndian; withUnsafeBytes(of: &x) { d.append(contentsOf: $0) } }
        str("RIFF"); u32(UInt32(36 + dataSize)); str("WAVE")
        str("fmt "); u32(16); u16(1); u16(1)            // PCM, mono
        u32(UInt32(sampleRate)); u32(UInt32(byteRate)); u16(2); u16(16)
        str("data"); u32(UInt32(dataSize))
        pcm16.withUnsafeBytes { d.append(contentsOf: $0) }
        return d
    }
}
