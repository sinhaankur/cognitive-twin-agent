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
        var prints: [[Float]]     // a few feature-print vectors
    }

    private var people: [Person] = []
    private let store: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask).first!
        return base.appendingPathComponent("Vera/faceid.json")
    }()
    // Distance below this = a confident match. Vision face-print distances are
    // typically ~0.3–0.6 for the same person, higher for different people. Tuned
    // conservative so a stranger is "someone", never a wrong name.
    private let matchThreshold: Float = 0.62

    private init() { load() }

    var enrolledNames: [String] { people.map(\.name) }
    var isEmpty: Bool { people.isEmpty }

    // MARK: recognition

    /// Name the person whose face occupies `box` in `pixels`, or nil if unknown /
    /// not confident. Runs entirely on-device.
    func identify(in pixels: CVPixelBuffer, box: CGRect) -> String? {
        guard !people.isEmpty, let print = featurePrint(of: pixels, box: box) else { return nil }
        var best: (name: String, dist: Float)? = nil
        for p in people {
            for enrolled in p.prints {
                if let d = Self.distance(print, enrolled) {
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
        guard let print = featurePrint(of: pixels, box: box) else { return currentCount(name) }
        if let i = people.firstIndex(where: { $0.name == name }) {
            people[i].prints.append(print)
            if people[i].prints.count > 8 { people[i].prints.removeFirst() }  // keep recent 8
        } else {
            people.append(Person(id: UUID().uuidString, name: name, prints: [print]))
        }
        save()
        return currentCount(name)
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
        people.first(where: { $0.name == name })?.prints.count ?? 0
    }

    // MARK: feature-print extraction

    private let ciContext = CIContext(options: nil)

    /// Crop the face box out of the frame and compute its Vision feature-print.
    private func featurePrint(of pixels: CVPixelBuffer, box: CGRect) -> [Float]? {
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

        let req = VNGenerateImageFeaturePrintRequest()
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try? handler.perform([req])
        guard let obs = req.results?.first as? VNFeaturePrintObservation else { return nil }
        return Self.vector(obs)
    }

    /// Pull the float vector out of a feature-print observation.
    private static func vector(_ obs: VNFeaturePrintObservation) -> [Float]? {
        let count = obs.elementCount
        guard obs.elementType == .float, count > 0 else { return nil }
        let data = obs.data
        return data.withUnsafeBytes { raw -> [Float] in
            let buf = raw.bindMemory(to: Float.self)
            return Array(buf.prefix(count))
        }
    }

    /// Euclidean distance between two prints (same length).
    private static func distance(_ a: [Float], _ b: [Float]) -> Float? {
        guard a.count == b.count, !a.isEmpty else { return nil }
        var sum: Float = 0
        for i in 0..<a.count { let d = a[i] - b[i]; sum += d * d }
        return sum.squareRoot()
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
