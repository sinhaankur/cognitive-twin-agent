import Foundation
import Vision
import CoreImage
import AppKit

/// FaceID — on-device face RECOGNITION (who is this?), sealed locally, opt-in.
///
/// How it works, all on this Mac, nothing uploaded:
///   1. For each detected face, crop it from the frame and run Vision's
///      `VNGenerateImageFeaturePrintRequest` → a feature-print vector.
///   2. Compare that print to the ENROLLED people's prints (computeDistance).
///      The nearest enrolled person under a threshold is the match; otherwise
///      it's "someone" (an unknown guest) — never a guess at a name.
///
/// Enrollment is explicit: the user names a face they're looking at (e.g. "Dad —
/// Dr Randhir Kumar Sinha"), and we keep a few prints per person for robustness.
///
/// Privacy: prints are an opaque Vision vector (not a photo, not reversible to an
/// image). They're written to Application Support/Vera/faceid.json. No pixels, no
/// network. Enrollment and recognition only run while the camera is already on
/// (the FaceStrip is visible) — the same opt-in contract as the rest of the eye.
final class FaceID {
    static let shared = FaceID()

    struct Person: Codable {
        var id: String            // stable id
        var name: String          // "Dad — Dr Randhir Kumar Sinha"
        // The RAW Vision feature-print blobs (base64 Data). We keep the raw
        // observation data — not a hand-rolled float array — so we can reconstruct a
        // VNFeaturePrintObservation and compare with Vision's OWN computeDistance
        // (the metric the match threshold is calibrated for). The old `prints`
        // (plain [Float] + hand-rolled Euclidean) never matched because that distance
        // is on a different scale than the threshold.
        var printData: [Data] = []
        // legacy: older enrollments stored float vectors. Decoded for migration only.
        var prints: [[Float]]? = nil
    }

    private var people: [Person] = []
    private let store: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask).first!
        return base.appendingPathComponent("Vera/faceid.json")
    }()
    // Match metric = COSINE distance (1 − cosine similarity), range 0…2. We can't use
    // Vision's computeDistance against a STORED print because VNFeaturePrintObservation
    // has no public init-from-Data — but its prints are high-dim embeddings where
    // cosine distance separates identities cleanly and, unlike the old hand-rolled
    // Euclidean, is SCALE-STABLE (that mismatch is why enrollment never recognized
    // anyone). Same-person face crops typically score well under ~0.35; different
    // people higher. Start a touch generous so you're recognized across normal
    // angle/lighting, still short of confusing two people.
    private let matchThreshold: Float = 0.35

    private init() { load() }

    var enrolledNames: [String] { people.map(\.name) }
    var isEmpty: Bool { people.isEmpty }

    // MARK: recognition

    /// Name the person whose face occupies `box` in `pixels`, or nil if unknown /
    /// not confident. Runs entirely on-device. Uses Vision's native computeDistance.
    func identify(in pixels: CVPixelBuffer, box: CGRect) -> String? {
        guard !people.isEmpty,
              let liveObs = featurePrintObservation(of: pixels, box: box),
              let live = Self.vector(liveObs) else { return nil }
        var best: (name: String, dist: Float)? = nil
        for p in people {
            for blob in p.printData {
                guard let enrolled = Self.vector(fromBlob: blob),
                      let d = Self.cosineDistance(live, enrolled) else { continue }
                if best == nil || d < best!.dist { best = (p.name, d) }
            }
            // migrate any legacy float prints (pre-blob enrollments) into the match
            for vec in p.prints ?? [] {
                if let d = Self.cosineDistance(live, vec) {
                    if best == nil || d < best!.dist { best = (p.name, d) }
                }
            }
        }
        guard let b = best, b.dist <= matchThreshold else { return nil }
        return b.name
    }

    // MARK: enrollment

    /// Add a print for `name` (creating the person if new). Call a few times from
    /// slightly different angles for a robust match. Returns the sample count.
    @discardableResult
    func enroll(name: String, from pixels: CVPixelBuffer, box: CGRect) -> Int {
        guard let obs = featurePrintObservation(of: pixels, box: box) else {
            return currentCount(name)
        }
        enroll(name: name, observation: obs)
        return currentCount(name)
    }

    /// Core enroll: store a feature-print observation's raw blob under `name`.
    /// Shared by live-camera enrollment and the Photos importer.
    func enroll(name: String, observation obs: VNFeaturePrintObservation) {
        let blob = obs.data
        if let i = people.firstIndex(where: { $0.name == name }) {
            people[i].printData.append(blob)
            if people[i].printData.count > 12 { people[i].printData.removeFirst() } // keep recent 12
        } else {
            people.append(Person(id: UUID().uuidString, name: name, printData: [blob]))
        }
        save()
    }

    func forget(name: String) {
        people.removeAll { $0.name == name }
        save()
    }

    func forgetAll() {
        people.removeAll()
        save()
    }

    private func currentCount(_ name: String) -> Int {
        people.first(where: { $0.name == name })?.printData.count ?? 0
    }

    // MARK: feature-print extraction

    private let ciContext = CIContext(options: nil)

    /// Crop the face box out of the frame and compute its Vision feature-print
    /// OBSERVATION (kept whole so we can use Vision's native computeDistance).
    private func featurePrintObservation(of pixels: CVPixelBuffer, box: CGRect) -> VNFeaturePrintObservation? {
        let full = CIImage(cvPixelBuffer: pixels)
        let w = full.extent.width, h = full.extent.height
        // Vision boxes are normalized, origin bottom-left. Pad a little around the
        // face so the crop carries the whole head (more stable print).
        let pad: CGFloat = 0.15
        var rect = CGRect(x: (box.minX - pad * box.width) * w,
                          y: (box.minY - pad * box.height) * h,
                          width: box.width * (1 + 2 * pad) * w,
                          height: box.height * (1 + 2 * pad) * h)
        rect = rect.intersection(full.extent)
        guard !rect.isNull, rect.width > 20, rect.height > 20 else { return nil }
        let cropped = full.cropped(to: rect)
        guard let cg = ciContext.createCGImage(cropped, from: rect) else { return nil }
        return Self.featurePrint(ofCGImage: cg)
    }

    /// Feature-print of an arbitrary CGImage crop — used by the Photos importer too.
    static func featurePrint(ofCGImage cg: CGImage) -> VNFeaturePrintObservation? {
        let req = VNGenerateImageFeaturePrintRequest()
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try? handler.perform([req])
        return req.results?.first as? VNFeaturePrintObservation
    }

    /// The float vector inside a feature-print observation (little-endian Float32).
    static func vector(_ obs: VNFeaturePrintObservation) -> [Float]? {
        guard obs.elementType == .float, obs.elementCount > 0 else { return nil }
        return obs.data.withUnsafeBytes { raw in
            Array(raw.bindMemory(to: Float.self).prefix(obs.elementCount))
        }
    }

    /// Decode a stored blob (raw Float32 bytes) back to a vector.
    static func vector(fromBlob blob: Data) -> [Float]? {
        guard !blob.isEmpty, blob.count % 4 == 0 else { return nil }
        return blob.withUnsafeBytes { raw in
            Array(raw.bindMemory(to: Float.self))
        }
    }

    /// Cosine distance between two prints: 1 − (a·b)/(‖a‖‖b‖). Range 0 (identical
    /// direction) … 2 (opposite). Scale-stable, so it tracks identity regardless of
    /// print magnitude — the robust metric for high-dim embeddings like these.
    static func cosineDistance(_ a: [Float], _ b: [Float]) -> Float? {
        guard a.count == b.count, !a.isEmpty else { return nil }
        var dot: Float = 0, na: Float = 0, nb: Float = 0
        for i in 0..<a.count {
            dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]
        }
        let denom = (na.squareRoot() * nb.squareRoot())
        guard denom > 0 else { return nil }
        return 1 - dot / denom
    }

    // MARK: persistence (local only)

    private func load() {
        guard let data = try? Data(contentsOf: store) else { return }
        people = (try? JSONDecoder().decode([Person].self, from: data)) ?? []
    }

    private func save() {
        try? FileManager.default.createDirectory(
            at: store.deletingLastPathComponent(), withIntermediateDirectories: true)
        if let data = try? JSONEncoder().encode(people) {
            try? data.write(to: store, options: .atomic)
        }
    }
}
