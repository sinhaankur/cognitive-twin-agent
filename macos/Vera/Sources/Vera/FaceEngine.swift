import AVFoundation
import SwiftUI
import Vision

/// Her eye, gone native: Apple's Vision face-landmark tracker (all on-device)
/// replaces the page's optical flow inside the app. The preview never shows
/// video — only the landmark dots, and the dots SPEAK: the mouth lights up
/// captioned "smile" when a smile is read, the brows when they knit, the eyes
/// on a blink. The server receives a few derived FACIAL facts per second
/// (present, energy, nod/shake, lean, smile, brow-knit, blink rate, attending)
/// — measured geometry, never guessed feelings. Frames never leave RAM.
///
/// Same privacy contract as before: the engine only runs while the preview
/// window exists; stop() — or the window closing — halts the camera and posts
/// /api/presence/stop so she forgets at once.
///
/// Threading: all vision + signal state lives on `queue`; only the published
/// draw-ready values hop to the main thread.
final class FaceEngine: NSObject, ObservableObject {
    struct Dot: Identifiable {
        let id: Int
        let x: CGFloat, y: CGFloat        // normalized view coords (mirrored, y down)
        let color: Color, alpha: Double, r: CGFloat
    }
    struct Caption: Identifiable {
        let id: String
        let text: String
        let x: CGFloat, y: CGFloat
        let color: Color
    }
    @Published var dots: [Dot] = []
    @Published var captions: [Caption] = []
    @Published var reading = ""                 // one honest line of what she reads
    @Published var status = "starting her eye…"

    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "vera.eye", qos: .userInitiated)
    private let sequence = VNSequenceRequestHandler()
    private var postTimer: Timer?

    // ---- state below is touched ONLY on `queue` -----------------------------
    // rolling histories (~1.5 s at 30 fps), same signal logic as the page's flow.js
    private var deltas: [(dx: CGFloat, dy: CGFloat)] = []
    private var lastCenter: CGPoint?
    private var iods: [CGFloat] = []
    // per-session neutral baseline (first ~1.5 s of a visible face): the honest
    // way to read expression change on THIS face, not against a canned average
    private var baseSamples: [(width: CGFloat, curve: CGFloat, brow: CGFloat, eye: CGFloat)] = []
    private var base: (width: CGFloat, curve: CGFloat, brow: CGFloat, eye: CGFloat)?
    private var blinkTimes: [Date] = []
    private var eyesClosed = false
    private var lastSeen: Date?
    private var smile = 0.0, browKnit = 0.0, energy = 0.0
    private var attending = true

    // ---- lifecycle (main thread) --------------------------------------------

    func start() {
        AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
            guard let self else { return }
            guard granted else { self.publish(status: "camera not allowed"); return }
            self.queue.async { self.configure() }
        }
        postTimer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.queue.async { self.postSignals() }
        }
    }

    func stop() {
        postTimer?.invalidate(); postTimer = nil
        queue.async { self.session.stopRunning() }
        Self.post(path: "/api/presence/stop", body: [:])   // she forgets immediately
    }

    private func configure() {
        guard let cam = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: cam) else {
            publish(status: "camera unavailable"); return
        }
        session.beginConfiguration()
        session.sessionPreset = .vga640x480
        if session.canAddInput(input) { session.addInput(input) }
        let out = AVCaptureVideoDataOutput()
        out.alwaysDiscardsLateVideoFrames = true
        out.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(out) { session.addOutput(out) }
        session.commitConfiguration()
        session.startRunning()
        publish(status: "face landmarks · on-device · close to stop")
    }

    private func publish(status s: String) {
        DispatchQueue.main.async { self.status = s }
    }

    // ---- geometry helpers ----------------------------------------------------

    private static func centroid(_ pts: [CGPoint]) -> CGPoint {
        var x: CGFloat = 0, y: CGFloat = 0
        for p in pts { x += p.x; y += p.y }
        return CGPoint(x: x / CGFloat(pts.count), y: y / CGFloat(pts.count))
    }
    private static func median(_ v: [CGFloat]) -> CGFloat {
        let s = v.sorted(); return s.isEmpty ? 0 : s[s.count / 2]
    }
    /// Landmark region → normalized image points (y up), via the face box.
    private static func imagePoints(_ r: VNFaceLandmarkRegion2D?, _ box: CGRect) -> [CGPoint] {
        guard let r else { return [] }
        return r.normalizedPoints.map {
            CGPoint(x: box.minX + $0.x * box.width, y: box.minY + $0.y * box.height)
        }
    }

    // ---- per-frame reading (on `queue`) ---------------------------------------

    private func ingest(_ face: VNFaceObservation?) {
        guard let face, let marks = face.landmarks else {
            if let seen = lastSeen, Date().timeIntervalSince(seen) > 1.5 {
                DispatchQueue.main.async {
                    self.dots = []; self.captions = []; self.reading = ""
                    self.status = "looking for you…"
                }
            }
            return
        }
        lastSeen = Date()
        let box = face.boundingBox
        let lEye  = Self.imagePoints(marks.leftEye, box)
        let rEye  = Self.imagePoints(marks.rightEye, box)
        let lBrow = Self.imagePoints(marks.leftEyebrow, box)
        let rBrow = Self.imagePoints(marks.rightEyebrow, box)
        let lips  = Self.imagePoints(marks.outerLips, box)
        let nose  = Self.imagePoints(marks.nose, box)
        let rim   = Self.imagePoints(marks.faceContour, box)
        guard lEye.count > 2, rEye.count > 2, lips.count > 3 else { return }

        let lC = Self.centroid(lEye), rC = Self.centroid(rEye)
        let iod = max(0.001, hypot(rC.x - lC.x, rC.y - lC.y))   // the face's own ruler

        // mouth geometry: width + corner rise, in units of inter-ocular distance
        let cornerL = lips.min { $0.x < $1.x }!, cornerR = lips.max { $0.x < $1.x }!
        let lipsC = Self.centroid(lips)
        let width = hypot(cornerR.x - cornerL.x, cornerR.y - cornerL.y) / iod
        let curve = ((cornerL.y + cornerR.y) / 2 - lipsC.y) / iod
        // brows: height above the eyes (knitting pulls them down + together)
        var browDist: CGFloat = 0
        if lBrow.count > 1, rBrow.count > 1 {
            browDist = ((Self.centroid(lBrow).y - lC.y) + (Self.centroid(rBrow).y - rC.y)) / 2 / iod
        }
        // eyes: aperture (height over width) — collapses on a blink
        func aperture(_ eye: [CGPoint]) -> CGFloat {
            let xs = eye.map(\.x), ys = eye.map(\.y)
            return (ys.max()! - ys.min()!) / max(0.001, xs.max()! - xs.min()!)
        }
        let eyeOpen = (aperture(lEye) + aperture(rEye)) / 2

        // neutral baseline for THIS session's face
        if base == nil {
            baseSamples.append((width, curve, browDist, eyeOpen))
            if baseSamples.count >= 45 {
                base = (Self.median(baseSamples.map(\.width)),
                        Self.median(baseSamples.map(\.curve)),
                        Self.median(baseSamples.map(\.brow)),
                        Self.median(baseSamples.map(\.eye)))
            }
        }
        if let b = base {
            let rawSmile = min(1, max(0, (width - b.width) / b.width * 5 + (curve - b.curve) * 12))
            smile = smile * 0.7 + rawSmile * 0.3
            let rawKnit = b.brow > 0 ? min(1, max(0, (b.brow - browDist) / (b.brow * 0.18))) : 0
            browKnit = browKnit * 0.7 + rawKnit * 0.3
            let closed = eyeOpen < b.eye * 0.55
            if eyesClosed && !closed { blinkTimes.append(Date()) }
            eyesClosed = closed
            blinkTimes.removeAll { Date().timeIntervalSince($0) > 20 }
        }

        // attention: yaw when Vision offers it, else nose-between-eyes asymmetry
        let mid = CGPoint(x: (lC.x + rC.x) / 2, y: (lC.y + rC.y) / 2)
        let proxy = nose.isEmpty ? 0 : Double((Self.centroid(nose).x - mid.x) / iod)
        let yaw = face.yaw?.doubleValue ?? proxy * 2
        attending = abs(yaw) < 0.35

        // motion: face-center deltas, same nod/shake/lean logic as flow.js
        let center = CGPoint(x: box.midX, y: box.midY)
        if let last = lastCenter {
            deltas.append((dx: (center.x - last.x) * 160, dy: (center.y - last.y) * 160))
            if deltas.count > 45 { deltas.removeFirst() }
        }
        lastCenter = center
        iods.append(iod)
        if iods.count > 45 { iods.removeFirst() }
        let meanMag = deltas.isEmpty ? 0 :
            deltas.map { hypot($0.dx, $0.dy) }.reduce(0, +) / CGFloat(deltas.count)
        energy = min(1, max(0, Double(meanMag) / 2.5))

        publishDots(rim: rim, lEye: lEye, rEye: rEye, lBrow: lBrow, rBrow: rBrow,
                    lips: lips, nose: nose)
    }

    private var gesture: String? {
        guard deltas.count > 10 else { return nil }
        var flipsX = 0, flipsY = 0
        var ampX: CGFloat = 0, ampY: CGFloat = 0
        for i in 1..<deltas.count {
            let a = deltas[i - 1], b = deltas[i]
            if abs(b.dy) > 0.35 && abs(a.dy) > 0.35 && b.dy.sign != a.dy.sign { flipsY += 1 }
            if abs(b.dx) > 0.35 && abs(a.dx) > 0.35 && b.dx.sign != a.dx.sign { flipsX += 1 }
            ampY = max(ampY, abs(b.dy)); ampX = max(ampX, abs(b.dx))
        }
        if flipsY >= 2 && ampY > ampX * 1.5 { return "nod" }
        if flipsX >= 2 && ampX > ampY * 1.5 { return "shake" }
        return nil
    }
    private var lean: String? {
        guard iods.count > 10, let s0 = iods.first, let s1 = iods.last, s0 > 0 else { return nil }
        if s1 > s0 * 1.09 { return "in" }
        if s1 < s0 * 0.91 { return "out" }
        return nil
    }
    private var present: Bool {
        if let seen = lastSeen { return Date().timeIntervalSince(seen) < 1.5 }
        return false
    }
    private var blinkRate: Double { Double(blinkTimes.count) * 3 }   // per minute

    // ---- the dots, and what they say ------------------------------------------

    private func publishDots(rim: [CGPoint], lEye: [CGPoint], rEye: [CGPoint],
                             lBrow: [CGPoint], rBrow: [CGPoint],
                             lips: [CGPoint], nose: [CGPoint]) {
        let cyan = Color(red: 0.49, green: 0.78, blue: 1)
        let gold = Color(red: 1, green: 0.85, blue: 0.45)
        let pink = Color(red: 0.94, green: 0.5, blue: 0.8)
        let blink = eyesClosed
        var out: [Dot] = []
        var id = 0
        func add(_ pts: [CGPoint], _ c: Color, _ a: Double, _ r: CGFloat) {
            for p in pts {                       // mirror x, flip y → view space
                out.append(Dot(id: id, x: 1 - p.x, y: 1 - p.y, color: c, alpha: a, r: r))
                id += 1
            }
        }
        add(rim, cyan, 0.35, 1.2)
        add(nose, cyan, 0.5, 1.2)
        add(lEye, blink ? .white : cyan, blink ? 1 : 0.8, 1.5)
        add(rEye, blink ? .white : cyan, blink ? 1 : 0.8, 1.5)
        add(lBrow, browKnit > 0.5 ? pink : cyan, 0.5 + browKnit * 0.5, 1.5)
        add(rBrow, browKnit > 0.5 ? pink : cyan, 0.5 + browKnit * 0.5, 1.5)
        add(lips, smile > 0.5 ? gold : cyan, 0.5 + smile * 0.5, 1.5)

        var caps: [Caption] = []
        if smile > 0.5 {
            let c = Self.centroid(lips)
            caps.append(Caption(id: "smile", text: "smile", x: 1 - c.x, y: 1 - c.y + 0.09, color: gold))
        }
        if browKnit > 0.5 {
            let c = Self.centroid(lBrow + rBrow)
            caps.append(Caption(id: "brow", text: "brow · knit", x: 1 - c.x, y: 1 - c.y - 0.08, color: pink))
        }

        var bits: [String] = []
        if smile > 0.5 { bits.append("smiling") }
        if browKnit > 0.5 { bits.append("brow knitted") }
        if blinkRate > 28 { bits.append("blinking fast") }
        bits.append(attending ? "attentive" : "looking away")
        bits.append(energy < 0.08 ? "very still" : energy < 0.28 ? "calm"
                    : energy < 0.6 ? "animated" : "very animated")
        let line = "reading: " + bits.joined(separator: " · ")

        DispatchQueue.main.async {
            self.dots = out
            self.captions = caps
            self.reading = line
            self.status = "face landmarks · on-device · close to stop"
        }
    }

    // ---- honest facts to the local server --------------------------------------

    private func postSignals() {
        var body: [String: Any] = ["present": present, "energy": energy, "source": "face"]
        if present {
            if let g = gesture { body["gesture"] = g }
            if let l = lean { body["lean"] = l }
            if base != nil {
                body["smile"] = (smile * 100).rounded() / 100
                body["brow"] = (browKnit * 100).rounded() / 100
                body["blink_rate"] = blinkRate
            }
            body["attending"] = attending
        }
        Self.post(path: "/api/presence", body: body)
    }

    private static func post(path: String, body: [String: Any]) {
        guard let url = URL(string: "http://127.0.0.1:7878" + path),
              let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        URLSession.shared.dataTask(with: req).resume()
    }
}

extension FaceEngine: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let pixels = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let request = VNDetectFaceLandmarksRequest()
        try? sequence.perform([request], on: pixels)
        let face = (request.results ?? []).max { $0.boundingBox.width < $1.boundingBox.width }
        ingest(face)          // delegate already runs on `queue`
    }
}
