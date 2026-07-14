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
        let group: Int                    // same group = one feature; -1 = loose dots
        let closes: Bool                  // group draws as a closed loop (lips, eyes)
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
    // live meters for the instrument row (what the dots are reading, as numbers)
    @Published var readSmile = 0.0
    @Published var readBrow = 0.0
    @Published var readFrown = 0.0              // mouth downturned (measured, not "sad")
    @Published var readBlink = 0.0              // blinks per minute
    @Published var readAttending = true
    @Published var facePresent = false
    @Published var lowLight = false             // dim room: reads steadier, says so

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
    private var smile = 0.0, browKnit = 0.0, frown = 0.0, energy = 0.0
    private var attending = true
    private var dimRoom = false
    // auto-framing: the face fills the little window (Face ID-style) and the
    // frame glides after you rather than jumping — smoothed centre + span
    private var frameC = CGPoint(x: 0.5, y: 0.5)
    private var frameS: CGFloat = 1.0
    // per-landmark temporal smoothing: Vision's points jitter a little every
    // frame; each landmark eases toward its new position, so the whole face
    // GLIDES — the single biggest "finished" cue in the preview
    private var smoothPts: [Int: CGPoint] = [:]

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
                smoothPts.removeAll()   // don't glide across an absence
                DispatchQueue.main.async {
                    self.dots = []; self.captions = []; self.reading = ""
                    self.facePresent = false
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
        let inner = Self.imagePoints(marks.innerLips, box)
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
            // the smile's mirror: corners sinking below this face's own neutral
            // — a measured mouth shape, reported as such, never as a feeling
            let rawFrown = min(1, max(0, (b.curve - curve) * 12 - rawSmile))
            frown = frown * 0.7 + rawFrown * 0.3
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
                    lips: lips, inner: inner, nose: nose)
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
                             lips: [CGPoint], inner: [CGPoint], nose: [CGPoint]) {
        let cyan = Color(red: 0.49, green: 0.78, blue: 1)
        let gold = Color(red: 1, green: 0.85, blue: 0.45)
        let pink = Color(red: 0.94, green: 0.5, blue: 0.8)
        let violet = Color(red: 0.7, green: 0.55, blue: 1)
        let blink = eyesClosed
        let lipTint = smile > 0.5 ? gold : (frown > 0.5 ? violet : cyan)
        let lipHot = max(smile, frown)

        // glide the frame: the face owns ~62% of the window, wherever you sit
        let all = rim + lEye + rEye + lBrow + rBrow + lips + nose
        let xs = all.map(\.x), ys = all.map(\.y)
        if let x0 = xs.min(), let x1 = xs.max(), let y0 = ys.min(), let y1 = ys.max() {
            let c = CGPoint(x: (x0 + x1) / 2, y: (y0 + y1) / 2)
            let span = max(0.05, max(x1 - x0, y1 - y0)) / 0.62
            frameC.x += (c.x - frameC.x) * 0.15
            frameC.y += (c.y - frameC.y) * 0.15
            frameS += (span - frameS) * 0.12
        }
        func map(_ p: CGPoint) -> (CGFloat, CGFloat) {
            // mirror + flip into view space, then centre inside the glided frame
            (0.5 + ((1 - p.x) - (1 - frameC.x)) / frameS,
             0.5 + ((1 - p.y) - (1 - frameC.y)) / frameS)
        }

        var out: [Dot] = []
        var id = 0
        func add(_ pts: [CGPoint], _ c: Color, _ a: Double, _ r: CGFloat,
                 group: Int, closes: Bool = false) {
            // in a dim room the landmarks shake more — steady them harder
            let ease: CGFloat = dimRoom ? 0.24 : 0.45
            for (i, raw) in pts.enumerated() {
                // temporal smoothing per landmark: ease toward the fresh
                // position so the face glides instead of jittering
                let key = group &* 1000 &+ i
                let prev = smoothPts[key] ?? raw
                let p = CGPoint(x: prev.x + (raw.x - prev.x) * ease,
                                y: prev.y + (raw.y - prev.y) * ease)
                smoothPts[key] = p
                let (x, y) = map(p)
                out.append(Dot(id: id, x: x, y: y, color: c, alpha: a, r: r,
                               group: group, closes: closes))
                id += 1
            }
        }
        add(rim, cyan, 0.35, 1.2, group: 0)                       // jawline arc
        add(nose, cyan, 0.5, 1.2, group: -1)                      // loose points
        add(lEye, blink ? .white : cyan, blink ? 1 : 0.8, 1.5, group: 2, closes: true)
        add(rEye, blink ? .white : cyan, blink ? 1 : 0.8, 1.5, group: 3, closes: true)
        add(lBrow, browKnit > 0.5 ? pink : cyan, 0.5 + browKnit * 0.5, 1.5, group: 4)
        add(rBrow, browKnit > 0.5 ? pink : cyan, 0.5 + browKnit * 0.5, 1.5, group: 5)
        add(lips, lipTint, 0.5 + lipHot * 0.5, 1.5, group: 6, closes: true)
        add(inner, lipTint, 0.35 + lipHot * 0.4, 1.2, group: 7, closes: true)

        var caps: [Caption] = []
        if smile > 0.5 {
            let (x, y) = map(Self.centroid(lips))
            caps.append(Caption(id: "smile", text: "smile",
                                x: x, y: min(0.85, y + 0.11), color: gold))
        }
        if browKnit > 0.5 {
            let (x, y) = map(Self.centroid(lBrow + rBrow))
            caps.append(Caption(id: "brow", text: "brow · knit",
                                x: x, y: max(0.08, y - 0.10), color: pink))
        }
        if frown > 0.5 && smile <= 0.5 {
            let (x, y) = map(Self.centroid(lips))
            caps.append(Caption(id: "down", text: "mouth · down",
                                x: x, y: min(0.85, y + 0.11), color: violet))
        }

        var bits: [String] = []
        if smile > 0.5 { bits.append("smiling") }
        if browKnit > 0.5 { bits.append("brow knitted") }
        if frown > 0.5 && smile <= 0.5 { bits.append("mouth downturned") }
        if blinkRate > 28 { bits.append("blinking fast") }
        bits.append(attending ? "attentive" : "looking away")
        bits.append(energy < 0.08 ? "very still" : energy < 0.28 ? "calm"
                    : energy < 0.6 ? "animated" : "very animated")
        let line = "reading: " + bits.joined(separator: " · ")

        let m = (smile, browKnit, frown, blinkRate, attending, dimRoom)
        DispatchQueue.main.async {
            self.dots = out
            self.captions = caps
            self.reading = line
            self.readSmile = m.0; self.readBrow = m.1; self.readFrown = m.2
            self.readBlink = m.3; self.readAttending = m.4
            self.lowLight = m.5
            self.facePresent = true
            self.status = m.5 ? "low light — steadying the read · on-device"
                              : "face landmarks · on-device · close to stop"
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
                body["frown"] = (frown * 100).rounded() / 100
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
        dimRoom = Self.isDim(pixels)
        let request = VNDetectFaceLandmarksRequest()
        try? sequence.perform([request], on: pixels)
        let face = (request.results ?? []).max { $0.boundingBox.width < $1.boundingBox.width }
        ingest(face)          // delegate already runs on `queue`
    }

    /// Mean luma of a sparse sample of the frame — a dim room makes Vision's
    /// landmarks jitter more, so the engine steadies harder and says so.
    private static func isDim(_ buffer: CVPixelBuffer) -> Bool {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        // plane 0 is luma for the common 420 formats macOS cameras deliver
        guard CVPixelBufferGetPlaneCount(buffer) > 0,
              let base = CVPixelBufferGetBaseAddressOfPlane(buffer, 0) else { return false }
        let w = CVPixelBufferGetWidthOfPlane(buffer, 0)
        let h = CVPixelBufferGetHeightOfPlane(buffer, 0)
        let stride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
        let p = base.assumingMemoryBound(to: UInt8.self)
        var sum = 0, n = 0
        var y = 0
        while y < h {
            var x = 0
            while x < w {
                sum += Int(p[y * stride + x]); n += 1
                x += 16
            }
            y += 16
        }
        return n > 0 && (sum / n) < 60      // of 255: a genuinely dim room
    }
}
