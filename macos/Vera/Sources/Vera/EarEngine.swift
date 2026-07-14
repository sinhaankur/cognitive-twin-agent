import AVFoundation
import SoundAnalysis
import SwiftUI

/// Her ear on the room — strictly behind the "Hear the room" switch. When ON,
/// Apple's built-in sound classifier (SoundAnalysis, all on-device) listens to
/// the ambient bed and reads honest, measured facts: "music", "typing",
/// "conversation" — each with its confidence — plus how loud the room is.
/// No audio is recorded or stored anywhere; the server keeps only the LATEST
/// reading and forgets the moment you switch off (or within seconds, by
/// staleness). Same contract as the eye: an explicit switch, a visible state,
/// measured facts only, never a mood invented from them.
///
/// Runs its own AVAudioEngine: on macOS the input HAL is multi-client, so the
/// ear and the voice turn-taking engine can listen at the same time.
final class EarEngine: NSObject, ObservableObject {
    @Published var on = false
    @Published var heard = ""                    // one line for the UI
    /// The room's verdict, for whoever needs it: true while the ambient bed is
    /// noisy enough that the voice mic should isolate (VoiceEngine listens).
    var onNoise: ((Bool) -> Void)?

    private let engine = AVAudioEngine()
    private var analyzer: SNAudioStreamAnalyzer?
    private var postTimer: Timer?
    // written on main only (observer + level both hop here)
    private var labels: [(String, Double)] = []
    private var loud: Double = 0

    func toggle() { on ? stop() : start() }

    func start() {
        guard !on else { return }
        AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
            DispatchQueue.main.async {
                guard granted, let self else { return }
                self.configure()
            }
        }
    }

    private func configure() {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        let analyzer = SNAudioStreamAnalyzer(format: format)
        if let request = try? SNClassifySoundRequest(classifierIdentifier: .version1) {
            // 1.5 s windows, half-overlapped: quick enough to feel live,
            // long enough that the classifier isn't guessing from a blip
            request.windowDuration = CMTime(seconds: 1.5, preferredTimescale: 48_000)
            request.overlapFactor = 0.5
            try? analyzer.add(request, withObserver: self)
        }
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, when in
            guard let self else { return }
            self.analyzer?.analyze(buffer, atAudioFramePosition: when.sampleTime)
            self.measure(buffer)
        }
        self.analyzer = analyzer
        engine.prepare()
        do { try engine.start() } catch { return }
        on = true
        heard = "listening to the room…"
        postTimer = Timer.scheduledTimer(withTimeInterval: 1.9, repeats: true) { [weak self] _ in
            self?.post()
        }
    }

    func stop() {
        guard on else { return }
        postTimer?.invalidate(); postTimer = nil
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        analyzer = nil
        labels = []; loud = 0
        on = false
        heard = ""
        onNoise?(false)                          // no ear, no isolation verdict
        Self.send(path: "/api/presence/ambient/stop", body: [:])   // she forgets at once
    }

    /// RMS → a rolling room loudness (0…1), independent of the classifier.
    private func measure(_ buffer: AVAudioPCMBuffer) {
        guard let ch = buffer.floatChannelData?[0] else { return }
        let n = Int(buffer.frameLength)
        var sum: Float = 0
        for i in 0..<n { sum += ch[i] * ch[i] }
        let rms = Double(min(1, sqrt(sum / Float(max(1, n))) * 8))
        DispatchQueue.main.async { self.loud = self.loud * 0.8 + rms * 0.2 }
    }

    private func post() {
        let sounds = labels.map { ["label": $0.0, "conf": ($0.1 * 100).rounded() / 100] }
        Self.send(path: "/api/presence/ambient",
                  body: ["sounds": sounds, "loud": (loud * 100).rounded() / 100])
    }

    private static func send(path: String, body: [String: Any]) {
        guard let url = URL(string: "http://127.0.0.1:7878" + path),
              let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        URLSession.shared.dataTask(with: req).resume()
    }
}

extension EarEngine: SNResultsObserving {
    func request(_ request: SNRequest, didProduce result: SNResult) {
        guard let r = result as? SNClassificationResult else { return }
        // only confident reads, and never more than three — an honest ear, not
        // a guess machine ("speech" here is the room, not transcription)
        let top = r.classifications.prefix(3)
            .filter { $0.confidence > 0.45 }
            .map { ($0.identifier.replacingOccurrences(of: "_", with: " "), Double($0.confidence)) }
        DispatchQueue.main.async {
            self.labels = top
            self.heard = top.isEmpty ? "quiet room"
                : "hearing: " + top.map(\.0).joined(separator: " · ")
            // a noisy bed (or plainly loud room) → the voice mic should isolate
            let noiseBed: Set<String> = ["music", "traffic", "crowd", "vacuum cleaner",
                                         "air conditioner", "engine", "wind", "rain",
                                         "white noise", "television"]
            let noisy = self.loud > 0.3 || top.contains { noiseBed.contains($0.0) }
            self.onNoise?(noisy)
        }
    }
}
