import AVFoundation
import AppKit
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
    /// One shared eye for the whole app. The EyeView preview drives it (start/stop
    /// with the window), and the voice loop READS its room/addressee signal
    /// (`likelyAddressingHer`, `facePresent`) to tell "you talking to me" from
    /// "background / someone else" — without opening a second camera session.
    @MainActor static let shared = FaceEngine()

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
    // ---- READING THE ROOM -----------------------------------------------------
    // How many people are present, how many are looking toward her, a plain
    // social-context line, and whether a voice right now is likely meant for
    // Vera (so she can respond to you, not jump into others' conversation).
    @Published var peopleCount = 0
    @Published var attendingCount = 0           // of those, how many face the camera
    @Published var roomContext = ""             // "with you", "a group · 2 looking her way", …
    @Published var likelyAddressingHer = true   // gate the listening side can read
    // Who the NEAREST face is, if it matches an enrolled person (on-device FaceID).
    // nil = unknown / not enrolled / recognition off. Drives the named room read.
    @Published var recognizedName: String? = nil
    // The nearest face's box + the last pixel buffer, kept so the UI can ENROLL
    // the person you're looking at ("this is Dad") on demand. Pixels stay in RAM.
    private var lastNearestBox: CGRect? = nil
    private var lastPixels: CVPixelBuffer? = nil

    private let session = AVCaptureSession()
    /// The live capture session, exposed read-only so an AVCaptureVideoPreviewLayer
    /// can show the REAL camera feed in the panel (FaceStrip) — the same session
    /// Vision already runs on, so there's no second camera and the opt-in/stop
    /// contract is unchanged. The preview is mirrored to match the landmark coords.
    var captureSession: AVCaptureSession { session }
    private let queue = DispatchQueue(label: "vera.eye", qos: .userInitiated)
    private var postTimer: Timer?
    // Vision throttle: run face-landmark detection at most this often (~13fps),
    // even though the camera delivers ~30fps. Halves CPU with no visible change.
    private static let visionMinInterval: CFTimeInterval = 1.0 / 13.0
    private var lastVisionAt: CFTimeInterval = 0
    // The built-in Mac camera delivers upright frames, so Vision reads the raw
    // buffer as .up. (The FaceStrip preview is mirrored for display only — that
    // never touches the buffer Vision analyzes, so detection isn't flipped.)
    private static let bufferOrientation: CGImagePropertyOrientation = .up

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
    // ---- FEELING OVER TIME ----------------------------------------------------
    // The snapshot (smiling / brow knit) says what's on the face NOW. The arc of
    // a conversation is in how it CHANGES: brightening, tensing, winding down.
    // We keep a short rolling history and read the slope — like optical flow for
    // affect — so Vera can respond to the shift, not just the still frame.
    private struct Affect { let t: Date; let smile: Double; let brow: Double
                            let frown: Double; let energy: Double }
    private var affectHistory: [Affect] = []
    private let affectWindow: TimeInterval = 30     // seconds we read the trend over
    // Published trend, each in -1…+1 (negative = falling, positive = rising):
    // Published MIRRORS for the UI — written ONLY on the main thread (see the
    // publish in `ingest`). Mutating an @Published off the main thread is the
    // SwiftUI "Publishing changes from background threads is not allowed" fault,
    // which corrupts/hangs the UI. The queue computes into the plain `q*` vars
    // below; main mirrors them here.
    @Published var trendMood = 0.0      // ↑ brightening (smile up / brow+frown down)
    @Published var trendTension = 0.0   // ↑ tensing (brow-knit / frown rising)
    @Published var trendEnergy = 0.0    // ↑ more animated, ↓ winding down / settling
    @Published var moodLine = ""        // one plain phrase, or "" when nothing's moving
    // queue-side source of truth for the trend (touched ONLY on `queue`).
    private var qTrendMood = 0.0
    private var qTrendTension = 0.0
    private var qTrendEnergy = 0.0
    private var qMoodLine = ""
    // auto-framing: the face fills the little window (Face ID-style) and the
    // frame glides after you rather than jumping — smoothed centre + span
    private var frameC = CGPoint(x: 0.5, y: 0.5)
    private var frameS: CGFloat = 1.0
    // The auto-frame, PUBLISHED so the camera preview can zoom to match. The
    // `dots` are already mapped into this framed space (face ≈ 62% of the window);
    // the live video must apply the SAME crop/zoom or the overlay won't sit on the
    // face. frameCenter is the face centre (mirrored view space, 0…1), frameSpan
    // the zoom denominator (smaller span = tighter crop). Updated on `queue`,
    // mirrored to these @Published on main.
    @Published var frameCenter = CGPoint(x: 0.5, y: 0.5)
    @Published var frameSpan: CGFloat = 1.0
    // per-landmark temporal smoothing: Vision's points jitter a little every
    // frame; each landmark eases toward its new position, so the whole face
    // GLIDES — the single biggest "finished" cue in the preview
    private var smoothPts: [Int: CGPoint] = [:]

    // ---- lifecycle (main thread) --------------------------------------------

    func start() {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized:
            self.queue.async { self.configure() }
        case .notDetermined:
            // first time — ask once. One user action (Allow) turns it on. If the
            // prompt is dismissed WITHOUT allowing, macOS marks it denied and won't
            // show the prompt again — so send the user to Settings rather than
            // leaving a dead "tap to allow" that does nothing.
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                guard let self else { return }
                if granted { self.queue.async { self.configure() } }
                else {
                    self.publish(status: "Camera needs you — opening System Settings ▸ Privacy ▸ Camera")
                    self.openCameraSettings()
                }
            }
        case .denied, .restricted:
            // already denied — macOS won't re-prompt, so OPEN Settings for them
            // (a tap should DO something, not just show a message).
            self.publish(status: "Turn the camera on in System Settings ▸ Privacy ▸ Camera")
            self.openCameraSettings()
        @unknown default:
            self.publish(status: "camera unavailable")
        }
        postTimer = Timer.scheduledTimer(withTimeInterval: 1.2, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.queue.async { self.postSignals() }
        }
    }

    /// Open the Camera privacy pane (async, so it never blocks the UI). The view
    /// can call this from an "Open Settings" button when the camera is denied.
    func openCameraSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera") else { return }
        DispatchQueue.global(qos: .userInitiated).async { NSWorkspace.shared.open(url) }
    }

    func stop() {
        postTimer?.invalidate(); postTimer = nil
        queue.async { self.session.stopRunning() }
        Self.post(path: "/api/presence/stop", body: [:])   // she forgets immediately
    }

    /// Enroll the face you're CURRENTLY looking at under `name` (on-device FaceID).
    /// Uses the most recent nearest-face crop; call a few times from slightly
    /// different angles for a robust match. Returns the sample count (0 = no face
    /// in frame right now). Everything stays on this Mac.
    @discardableResult
    func enrollCurrentFace(as name: String) -> Int {
        guard let box = lastNearestBox, let pixels = lastPixels else { return 0 }
        let n = FaceID.shared.enroll(name: name, from: pixels, box: box)
        // refresh the live read so the name shows at once — the identify pass is a
        // Vision feature-print (not free), so run it OFF the main thread and only
        // publish the name back on main (never block the UI on enroll).
        queue.async { [weak self] in
            let who = FaceID.shared.identify(in: pixels, box: box)
            DispatchQueue.main.async { self?.recognizedName = who }
        }
        return n
    }

    /// Is a face in frame right now (so the UI can offer "name this person")?
    var hasFaceToEnroll: Bool { lastNearestBox != nil }

    private func configure() {
        // pick a REAL camera. AVCaptureDevice.default(for:.video) can hand back a
        // Continuity Camera (your iPhone) that isn't actually present/ready, so the
        // session "configures" but no frames ever arrive — looks like the camera
        // just won't turn on. Prefer the built-in Mac camera; fall back sensibly.
        let cam = Self.bestCamera()
        guard let cam, let input = try? AVCaptureDeviceInput(device: cam) else {
            publish(status: "no camera found — is one connected / not in use elsewhere?")
            return
        }
        session.beginConfiguration()
        session.sessionPreset = .vga640x480
        // clear any stale inputs/outputs from a previous attempt
        session.inputs.forEach { session.removeInput($0) }
        session.outputs.forEach { session.removeOutput($0) }
        if session.canAddInput(input) { session.addInput(input) }
        else { session.commitConfiguration(); publish(status: "couldn't open \(cam.localizedName)"); return }
        let out = AVCaptureVideoDataOutput()
        out.alwaysDiscardsLateVideoFrames = true
        out.setSampleBufferDelegate(self, queue: queue)
        if session.canAddOutput(out) { session.addOutput(out) }
        session.commitConfiguration()
        session.startRunning()
        publish(status: session.isRunning
                ? "seeing you · \(cam.localizedName) · on-device · close to stop"
                : "camera didn't start — try closing other apps using it")
    }

    /// The best camera to use: the built-in Mac camera first (reliable), then any
    /// non-Continuity external, then whatever's available. Avoids silently picking
    /// an iPhone Continuity Camera that isn't ready.
    private static func bestCamera() -> AVCaptureDevice? {
        // discover just the built-in camera type (Continuity/externals are found by
        // the default fallback). Built-in is the reliable one and avoids silently
        // grabbing an iPhone Continuity Camera that isn't ready.
        let builtin = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.builtInWideAngleCamera],
            mediaType: .video, position: .unspecified).devices.first
        if let builtin { return builtin }
        // no built-in → whatever the system offers (external webcam / Continuity)
        return AVCaptureDevice.default(for: .video)
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

        // feeling OVER TIME: fold this sample in and read the slope.
        updateAffectTrend()

        var bits: [String] = []
        if smile > 0.5 { bits.append("smiling") }
        if browKnit > 0.5 { bits.append("brow knitted") }
        if frown > 0.5 && smile <= 0.5 { bits.append("mouth downturned") }
        if blinkRate > 28 { bits.append("blinking fast") }
        bits.append(attending ? "attentive" : "looking away")
        bits.append(energy < 0.08 ? "very still" : energy < 0.28 ? "calm"
                    : energy < 0.6 ? "animated" : "very animated")
        // the trend, when something is actually moving, reads last
        if !qMoodLine.isEmpty { bits.append(qMoodLine) }
        let line = "reading: " + bits.joined(separator: " · ")

        let m = (smile, browKnit, frown, blinkRate, attending, dimRoom)
        let fc = frameC, fs = frameS
        // snapshot the queue-side trend so the UI mirror is set on MAIN (never
        // publish an @Published from this background queue — that hangs SwiftUI).
        let tm = qTrendMood, tt = qTrendTension, te = qTrendEnergy, ml = qMoodLine
        DispatchQueue.main.async {
            self.dots = out
            self.captions = caps
            self.reading = line
            self.readSmile = m.0; self.readBrow = m.1; self.readFrown = m.2
            self.readBlink = m.3; self.readAttending = m.4
            self.lowLight = m.5
            self.facePresent = true
            self.trendMood = tm; self.trendTension = tt
            self.trendEnergy = te; self.moodLine = ml
            self.frameCenter = fc; self.frameSpan = fs    // let the preview zoom to match
            self.status = m.5 ? "low light — steadying the read · on-device"
                              : "face landmarks · on-device · close to stop"
        }
    }

    // ---- honest facts to the local server --------------------------------------

    /// Fold the current expression into the rolling history and read its slope —
    /// the arc of feeling, not the still frame. Trends are least-squares slopes
    /// over the last `affectWindow` seconds, scaled so a clear change lands near
    /// ±1. Only a sustained move (not frame jitter) produces a `moodLine`.
    private func updateAffectTrend() {
        let now = Date()
        affectHistory.append(Affect(t: now, smile: smile, brow: browKnit,
                                    frown: frown, energy: energy))
        // drop anything older than the window
        affectHistory.removeAll { now.timeIntervalSince($0.t) > affectWindow }
        // need a few seconds of history before a trend means anything
        guard let first = affectHistory.first,
              affectHistory.count >= 5,
              now.timeIntervalSince(first.t) >= 6 else {
            qTrendMood = 0; qTrendTension = 0; qTrendEnergy = 0; qMoodLine = ""
            return
        }
        // least-squares slope of y against seconds, over the window
        func slope(_ pick: (Affect) -> Double) -> Double {
            let t0 = first.t
            let xs = affectHistory.map { $0.t.timeIntervalSince(t0) }
            let ys = affectHistory.map(pick)
            let n = Double(xs.count)
            let mx = xs.reduce(0,+) / n, my = ys.reduce(0,+) / n
            var num = 0.0, den = 0.0
            for i in 0..<xs.count { num += (xs[i]-mx)*(ys[i]-my); den += (xs[i]-mx)*(xs[i]-mx) }
            return den == 0 ? 0 : num/den      // units: per second
        }
        // scale per-second slope by the window so a full 0→1 swing ≈ ±1
        let k = affectWindow
        let sSmile = slope { $0.smile } * k
        let sBrow  = slope { $0.brow } * k
        let sFrown = slope { $0.frown } * k
        let sEnergy = slope { $0.energy } * k
        func clamp(_ v: Double) -> Double { min(1, max(-1, v)) }
        // mood rises when the smile grows and the brow/frown ease
        qTrendMood    = clamp(sSmile - 0.5 * sBrow - 0.5 * sFrown)
        qTrendTension = clamp(0.6 * sBrow + 0.4 * sFrown)
        qTrendEnergy  = clamp(sEnergy)

        // plain words, only when a move is real (hysteresis so it doesn't flicker)
        let strong = 0.22
        if qTrendTension > strong && qTrendTension > qTrendMood {
            qMoodLine = "tensing a little"
        } else if qTrendMood > strong {
            qMoodLine = "brightening"
        } else if qTrendMood < -strong {
            qMoodLine = "dimming a little"
        } else if qTrendEnergy < -strong {
            qMoodLine = "winding down"
        } else if qTrendEnergy > strong {
            qMoodLine = "picking up"
        } else {
            qMoodLine = ""
        }
    }

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
                // FEELING OVER TIME — the arc, so she can respond to the shift
                // ("you've been brightening", "you seem to be winding down"), not
                // just the still frame. Only sent when a trend is actually moving.
                if !qMoodLine.isEmpty {
                    body["trend"] = qMoodLine
                    body["trend_mood"] = (qTrendMood * 100).rounded() / 100
                    body["trend_tension"] = (qTrendTension * 100).rounded() / 100
                    body["trend_energy"] = (qTrendEnergy * 100).rounded() / 100
                }
            }
            body["attending"] = attending
        }
        // Reading the room — always sent (even with no primary face, there may
        // be people in view). Lets the server/agent know the social context so a
        // voice can be routed as "to Vera" vs. "room chatter". Snapshot the
        // main-thread values; a frame's staleness here is harmless.
        let people = peopleCountSnapshot
        body["people"] = people
        body["people_attending"] = attendingCountSnapshot
        if !roomContextSnapshot.isEmpty { body["room_context"] = roomContextSnapshot }
        body["addressing_her"] = likelyAddressingHerSnapshot
        // WHO she's with, if recognized on-device — so her brain can greet them by
        // name ("Hello again, Dad"). Just the name; no image ever leaves.
        if let who = recognizedNameSnapshot { body["recognized"] = who }
        Self.post(path: "/api/presence", body: body)
    }

    // queue-side mirrors of the published room values, updated alongside them so
    // postSignals() (on `queue`) reads them without hopping threads.
    private var peopleCountSnapshot = 0
    private var attendingCountSnapshot = 0
    private var roomContextSnapshot = ""
    private var likelyAddressingHerSnapshot = true
    private var recognizedNameSnapshot: String? = nil

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
        // THROTTLE Vision to ~13fps. The camera delivers 30fps, but running the
        // (neural) face-landmark detector on EVERY frame is the bulk of the app's
        // CPU while "See me" is on. A face's expression/pose doesn't change
        // meaningfully faster than ~13fps, and the per-landmark temporal smoothing
        // already glides between reads — so this halves the CPU with no visible
        // change in how she sees you. Frames in between are simply dropped
        // (alwaysDiscardsLateVideoFrames is already set).
        let now = CACurrentMediaTime()
        if now - lastVisionAt < Self.visionMinInterval { return }
        lastVisionAt = now

        dimRoom = Self.isDim(pixels)
        // TWO passes, on purpose:
        //  • Rectangles finds EVERY face in frame (reliable multi-face count) — this
        //    is what "reads the room": how many people, how many looking her way.
        //  • Landmarks runs on the nearest face for the expression/emotion read.
        // (A single landmarks request often returns only the strongest face, which
        //  is why the room showed "just you" even with two people in frame.)
        //
        // Both requests run on ONE fresh per-frame VNImageRequestHandler — the same
        // cost as the old single call, but NOT the VNSequenceRequestHandler. The
        // sequence handler is tuned for tracking ONE subject across frames and was
        // under-counting a second person (the screen read "just you" with two people
        // clearly in frame). A per-frame image handler, with the face detector
        // pinned to its newest revision (best multi-face recall) and an explicit
        // orientation (so an angled second face isn't missed), reliably finds
        // everyone — without adding a second Vision pass per frame.
        let rectReq = VNDetectFaceRectanglesRequest()
        if let newest = VNDetectFaceRectanglesRequest.supportedRevisions.max() {
            rectReq.revision = newest
        }
        let landmarkReq = VNDetectFaceLandmarksRequest()
        let handler = VNImageRequestHandler(cvPixelBuffer: pixels,
                                            orientation: Self.bufferOrientation,
                                            options: [:])
        try? handler.perform([rectReq, landmarkReq])
        let allFaces = rectReq.results ?? []
        let landmarked = landmarkReq.results ?? []
        // Prefer the richer set for the room count (rectangles usually ≥ landmarks).
        readRoom(allFaces.count >= landmarked.count ? allFaces : landmarked)
        let face = landmarked.max { $0.boundingBox.width < $1.boundingBox.width }
        ingest(face)          // delegate already runs on `queue`

        // On-device FACE ID: who is the nearest face? (opt-in via enrolled people;
        // no-op + nil when nobody is enrolled). Keep the box + pixels so the UI can
        // enroll "this is Dad" for the face you're currently looking at.
        let nearest = (allFaces.count >= landmarked.count
                       ? allFaces.max { $0.boundingBox.width < $1.boundingBox.width }
                       : face)
        let nearestBox = nearest?.boundingBox
        self.lastNearestBox = nearestBox
        let name: String? = nearestBox.flatMap { FaceID.shared.identify(in: pixels, box: $0) }
        recognizedNameSnapshot = name
        DispatchQueue.main.async { self.recognizedName = name }

        // IMPORTANT (freeze fix): the camera vends frames from a SMALL fixed pool.
        // We keep one frame around so "Who is this?" can enroll the face you're
        // looking at — but retaining the camera's own CVPixelBuffer past this
        // callback starves that pool, and the capture thread then stalls waiting
        // for a free buffer → the whole preview freezes. So we hand enrollment a
        // DEEP COPY and let the original buffer go back to the pool immediately.
        self.lastPixels = nearestBox != nil ? Self.copyPixelBuffer(pixels) : nil
    }

    /// Deep-copy a CVPixelBuffer so we can hold it past the capture callback
    /// without starving the camera's buffer pool (which would freeze the preview).
    private static func copyPixelBuffer(_ src: CVPixelBuffer) -> CVPixelBuffer? {
        let w = CVPixelBufferGetWidth(src)
        let h = CVPixelBufferGetHeight(src)
        let fmt = CVPixelBufferGetPixelFormatType(src)
        var dst: CVPixelBuffer?
        let attrs: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:]]
        guard CVPixelBufferCreate(kCFAllocatorDefault, w, h, fmt,
                                  attrs as CFDictionary, &dst) == kCVReturnSuccess,
              let out = dst else { return nil }
        CVPixelBufferLockBaseAddress(src, .readOnly)
        CVPixelBufferLockBaseAddress(out, [])
        defer {
            CVPixelBufferUnlockBaseAddress(out, [])
            CVPixelBufferUnlockBaseAddress(src, .readOnly)
        }
        let planes = max(1, CVPixelBufferGetPlaneCount(src))
        if CVPixelBufferIsPlanar(src) {
            for p in 0..<planes {
                guard let s = CVPixelBufferGetBaseAddressOfPlane(src, p),
                      let d = CVPixelBufferGetBaseAddressOfPlane(out, p) else { return nil }
                let bytes = CVPixelBufferGetBytesPerRowOfPlane(src, p)
                      * CVPixelBufferGetHeightOfPlane(src, p)
                memcpy(d, s, bytes)
            }
        } else {
            guard let s = CVPixelBufferGetBaseAddress(src),
                  let d = CVPixelBufferGetBaseAddress(out) else { return nil }
            memcpy(d, s, CVPixelBufferGetBytesPerRow(src) * h)
        }
        return out
    }

    /// Count people and infer the social context from every visible face:
    /// is the user speaking to Vera, or to other people in the room?
    ///
    /// Signals, all measured (never guessed): the number of faces, and for each
    /// its yaw — a face turned toward the camera (|yaw| small) is "attending"
    /// (looking at her). From these we read a plain context so she can decide
    /// whether a nearby voice is meant for her:
    ///   • 0 faces            → "no one in view"
    ///   • 1, attending       → "with you"            (talking to her)
    ///   • 1, looking away    → "you, turned away"    (maybe not to her)
    ///   • 2+, ≥1 attending   → "a group, X looking over"  (some address her)
    ///   • 2+, none attending → "people talking"      (room chatter, not her)
    private func readRoom(_ faces: [VNFaceObservation]) {
        let count = faces.count
        // A face counts as "looking at her" when it's turned roughly toward the
        // camera — same yaw threshold the single-face attention uses.
        let attendingCount = faces.filter { f in
            abs(f.yaw?.doubleValue ?? 1.0) < 0.35
        }.count

        let context: String
        switch count {
        case 0:  context = "no one in view"
        case 1:  context = attendingCount == 1 ? "with you" : "you, turned away"
        default:
            context = attendingCount == 0
                ? "people talking (not to her)"
                : "a group · \(attendingCount) looking her way"
        }
        // "Is this voice likely meant for Vera?" — true when exactly one person
        // is present and attending, OR (in a group) at least one person is
        // looking at her. This is the hook the listening side can gate on.
        let addressingHer = (count == 1 && attendingCount == 1) ||
                            (count >= 2 && attendingCount >= 1)

        // queue-side mirrors for postSignals() (we're already on `queue` here)
        peopleCountSnapshot = count
        attendingCountSnapshot = attendingCount
        roomContextSnapshot = context
        likelyAddressingHerSnapshot = addressingHer

        DispatchQueue.main.async {
            self.peopleCount = count
            self.attendingCount = attendingCount
            self.roomContext = context
            self.likelyAddressingHer = addressingHer
        }
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
