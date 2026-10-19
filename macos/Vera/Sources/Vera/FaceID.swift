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
        // Enrolled embeddings as raw Float32 bytes. We compare with cosine distance
        // (scale-stable, the right metric for these hypersphere embeddings — the old
        // hand-rolled Euclidean vs a mismatched threshold is why nobody ever matched).
        var printData: [Data] = []
        // Which model produced `printData` — we must NEVER compare an ArcFace vector
        // against a general-image-embedding vector (different spaces, meaningless
        // distance). "arcface" = the bundled face model; "vnprint" = Apple's general
        // feature print. Defaults to vnprint for pre-tag enrollments.
        var model: String = "vnprint"
        // legacy: older enrollments stored float vectors. Decoded for migration only.
        var prints: [[Float]]? = nil
    }

    /// Which embedding model is active right now — the real face model if bundled,
    /// else Apple's general print. Stored with each enrollment so we only ever
    /// compare like-with-like.
    private var activeModelKind: String { FaceEmbedder.shared != nil ? "arcface" : "vnprint" }

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
    /// not confident. Runs entirely on-device. Prefers the real face model (ArcFace)
    /// when bundled; compares with cosine distance; only against same-model prints.
    func identify(in pixels: CVPixelBuffer, box: CGRect) -> String? {
        guard !people.isEmpty, let cg = Self.crop(of: pixels, box: box),
              let live = embedVector(cg) else { return nil }
        let kind = activeModelKind
        var best: (name: String, dist: Float)? = nil
        for p in people where p.model == kind {   // never cross model spaces
            for blob in p.printData {
                guard let enrolled = Self.vector(fromBlob: blob),
                      let d = Self.cosineDistance(live, enrolled) else { continue }
                if best == nil || d < best!.dist { best = (p.name, d) }
            }
            // migrate any legacy float prints (pre-blob, general-embedding only)
            if kind == "vnprint" {
                for vec in p.prints ?? [] {
                    if let d = Self.cosineDistance(live, vec) {
                        if best == nil || d < best!.dist { best = (p.name, d) }
                    }
                }
            }
        }
        guard let b = best, b.dist <= matchThreshold else { return nil }
        return b.name
    }

    /// The identity embedding for a face crop — the REAL face model when bundled,
    /// else Apple's general image feature-print. L2-normalized either way so cosine
    /// distance is meaningful.
    private func embedVector(_ cg: CGImage) -> [Float]? {
        if let arc = FaceEmbedder.shared, let v = arc.embed(cgImage: cg) { return v }
        guard let obs = Self.featurePrint(ofCGImage: cg), let v = Self.vector(obs) else { return nil }
        return v
    }

    // MARK: enrollment

    /// Enroll the face in `box` from a camera/photo frame. Call a few times from
    /// slightly different angles for a robust match. Returns the sample count.
    @discardableResult
    func enroll(name: String, from pixels: CVPixelBuffer, box: CGRect) -> Int {
        guard let cg = Self.crop(of: pixels, box: box), let v = embedVector(cg) else {
            return currentCount(name)
        }
        enroll(name: name, vector: v)
        return currentCount(name)
    }

    /// Enroll directly from a face-cropped CGImage (the Photos importer path).
    @discardableResult
    func enroll(name: String, faceCrop cg: CGImage) -> Int {
        guard let v = embedVector(cg) else { return currentCount(name) }
        enroll(name: name, vector: v)
        return currentCount(name)
    }

    /// Core enroll: store an embedding under `name`, tagged with the active model so
    /// we only ever compare like-with-like. Shared by camera + Photos import.
    func enroll(name: String, vector v: [Float]) {
        let blob = v.withUnsafeBytes { Data($0) }
        let kind = activeModelKind
        if let i = people.firstIndex(where: { $0.name == name && $0.model == kind }) {
            people[i].printData.append(blob)
            if people[i].printData.count > 12 { people[i].printData.removeFirst() } // keep recent 12
        } else {
            people.append(Person(id: UUID().uuidString, name: name,
                                 printData: [blob], model: kind))
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
        let kind = activeModelKind
        return people.first(where: { $0.name == name && $0.model == kind })?.printData.count ?? 0
    }

    // MARK: feature-print extraction

    private let ciContext = CIContext(options: nil)

    /// Crop the face box out of a frame into a CGImage (padded to carry the head).
    static func crop(of pixels: CVPixelBuffer, box: CGRect) -> CGImage? {
        let full = CIImage(cvPixelBuffer: pixels)
        let w = full.extent.width, h = full.extent.height
        // Vision boxes are normalized, origin bottom-left. Pad a little around the
        // face so the crop carries the whole head (more stable embedding).
        let pad: CGFloat = 0.15
        var rect = CGRect(x: (box.minX - pad * box.width) * w,
                          y: (box.minY - pad * box.height) * h,
                          width: box.width * (1 + 2 * pad) * w,
                          height: box.height * (1 + 2 * pad) * h)
        rect = rect.intersection(full.extent)
        guard !rect.isNull, rect.width > 20, rect.height > 20 else { return nil }
        return sharedCtx.createCGImage(full.cropped(to: rect), from: rect)
    }
    private static let sharedCtx = CIContext(options: nil)

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
