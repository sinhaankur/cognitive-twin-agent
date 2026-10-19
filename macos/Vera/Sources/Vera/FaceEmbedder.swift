import Foundation
import CoreML
import Vision
import CoreImage

/// FaceEmbedder — REAL face-identity embeddings, the way FaceNet/ArcFace (and the
/// brain's fusiform face area) do it: a face-TRAINED model maps an aligned face to
/// a vector on a hypersphere, where cosine distance separates identities.
///
/// Apple ships face DETECTION but no public face-RECOGNITION model, so we bundle an
/// open ArcFace model converted to Core ML (see `build-face-model.sh`). It runs on
/// the Neural Engine, on-device, nothing uploaded.
///
/// GRACEFUL: if the model isn't bundled (you skipped the conversion step), `shared`
/// is nil and FaceID falls back to Apple's general image embedding. The app always
/// works; it just gets sharper when the real model is present.
final class FaceEmbedder {
    static let shared: FaceEmbedder? = FaceEmbedder()

    private let model: MLModel
    private let inputName: String
    private let inputSize: Int           // ArcFace = 112
    private let ciContext = CIContext(options: nil)

    private init?() {
        // compiled model in the app bundle's Resources (build-app.sh copies it).
        guard let url = Bundle.main.url(forResource: "FaceEmbedder", withExtension: "mlmodelc")
                ?? Bundle.main.url(forResource: "FaceEmbedder", withExtension: "mlmodel") else {
            return nil
        }
        let cfg = MLModelConfiguration()
        cfg.computeUnits = .all               // Neural Engine when available
        guard let m = try? MLModel(contentsOf: url) else { return nil }
        self.model = m
        // discover the image input name + expected size from the model description,
        // so we don't hardcode a name that might differ per conversion.
        guard let feature = m.modelDescription.inputDescriptionsByName.first(where: {
            $0.value.type == .image
        }) else { return nil }
        self.inputName = feature.key
        if let c = feature.value.imageConstraint {
            self.inputSize = c.pixelsWide
        } else {
            self.inputSize = 112
        }
    }

    /// Embed an already-cropped, aligned face image → an L2-normalized identity
    /// vector. Returns nil if the model can't run on it.
    func embed(cgImage cg: CGImage) -> [Float]? {
        guard let pixel = Self.pixelBuffer(from: cg, size: inputSize, ci: ciContext) else { return nil }
        guard let provider = try? MLDictionaryFeatureProvider(
            dictionary: [inputName: MLFeatureValue(pixelBuffer: pixel)]) else { return nil }
        guard let out = try? model.prediction(from: provider) else { return nil }
        // take the first multiarray output (the embedding)
        for name in out.featureNames {
            if let arr = out.featureValue(for: name)?.multiArrayValue {
                return Self.l2normalized(arr)
            }
        }
        return nil
    }

    // ArcFace wants a square RGB crop at `size`×`size`. (Normalization to [-1,1] is
    // baked into the converted model's preprocessing — see build-face-model.sh.)
    private static func pixelBuffer(from cg: CGImage, size: Int, ci: CIContext) -> CVPixelBuffer? {
        var pb: CVPixelBuffer?
        let attrs = [kCVPixelBufferCGImageCompatibilityKey: true,
                     kCVPixelBufferCGBitmapContextCompatibilityKey: true] as CFDictionary
        guard CVPixelBufferCreate(kCFAllocatorDefault, size, size,
                                  kCVPixelFormatType_32BGRA, attrs, &pb) == kCVReturnSuccess,
              let buffer = pb else { return nil }
        let src = CIImage(cgImage: cg)
        let scale = CGFloat(size) / max(src.extent.width, src.extent.height)
        let scaled = src.transformed(by: .init(scaleX: scale, y: scale))
        ci.render(scaled, to: buffer)
        return buffer
    }

    private static func l2normalized(_ arr: MLMultiArray) -> [Float] {
        let n = arr.count
        var v = [Float](repeating: 0, count: n)
        let ptr = arr.dataPointer
        switch arr.dataType {
        case .float32:
            let p = ptr.bindMemory(to: Float.self, capacity: n)
            for i in 0..<n { v[i] = p[i] }
        case .double:
            let p = ptr.bindMemory(to: Double.self, capacity: n)
            for i in 0..<n { v[i] = Float(p[i]) }
        default:
            for i in 0..<n { v[i] = arr[i].floatValue }
        }
        var mag: Float = 0
        for x in v { mag += x * x }
        mag = mag.squareRoot()
        if mag > 0 { for i in 0..<n { v[i] /= mag } }
        return v
    }
}
