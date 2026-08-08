import SwiftUI
import SceneKit

/// A loved one, held in 3D inside the orb — the "living photo." (iOS twin of the
/// macOS PortraitOrb; SceneKit on iOS uses Float vectors and UIViewRepresentable.)
///
/// A Blender-built USDZ relief (their real photo, displaced by AI-estimated depth
/// — no invented geometry) rendered live with a slow parallax turn and a drifting
/// key light, so the face feels present rather than flat.
///
/// HONESTY / QUALITY RULES, matching the rest of Vera:
///   • Opt-in only. Runs only when the switch is on AND a real mesh exists.
///   • Broken must never animate. No USDZ → this view is EmptyView; the orb
///     renders exactly as it always has. A face only appears when it is real.
///   • Local only. The mesh is a file on this device; nothing is fetched or sent.
struct PortraitOrb: View {
    let meshURL: URL?
    var phase: CGFloat

    var body: some View {
        if let url = meshURL, FileManager.default.fileExists(atPath: url.path) {
            PortraitSceneView(meshURL: url, phase: phase)
                .clipShape(Circle())
                .allowsHitTesting(false)
        } else {
            EmptyView()
        }
    }
}

private struct PortraitSceneView: UIViewRepresentable {
    let meshURL: URL
    var phase: CGFloat

    func makeUIView(context: Context) -> SCNView {
        let view = SCNView()
        view.backgroundColor = .clear
        view.antialiasingMode = .multisampling4X
        view.rendersContinuously = true
        view.scene = context.coordinator.buildScene(from: meshURL)
        return view
    }

    func updateUIView(_ view: SCNView, context: Context) {
        context.coordinator.update(phase: phase)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        private var faceNode: SCNNode?
        private var keyLightNode: SCNNode?

        func buildScene(from url: URL) -> SCNScene {
            let scene = (try? SCNScene(url: url, options: [
                .checkConsistency: true,
                .convertToYUp: true,
            ])) ?? SCNScene()

            let face = scene.rootNode.childNodes.first { $0.geometry != nil }
                ?? scene.rootNode
            let (minB, maxB) = face.boundingBox
            let center = SCNVector3((minB.x + maxB.x) / 2,
                                    (minB.y + maxB.y) / 2,
                                    (minB.z + maxB.z) / 2)
            face.pivot = SCNMatrix4MakeTranslation(center.x, center.y, center.z)
            faceNode = face

            let cam = SCNNode()
            cam.camera = SCNCamera()
            cam.camera?.fieldOfView = 28
            cam.position = SCNVector3(0, 0, 2.6)
            scene.rootNode.addChildNode(cam)

            let fill = SCNNode()
            fill.light = SCNLight()
            fill.light?.type = .ambient
            fill.light?.intensity = 320
            scene.rootNode.addChildNode(fill)

            let key = SCNNode()
            key.light = SCNLight()
            key.light?.type = .omni
            key.light?.intensity = 900
            key.position = SCNVector3(1.4, 1.0, 2.2)
            scene.rootNode.addChildNode(key)
            keyLightNode = key

            return scene
        }

        func update(phase: CGFloat) {
            let p = Double(phase)
            let yaw = sin(p * 0.18) * (7.0 * .pi / 180.0)
            faceNode?.eulerAngles.y = Float(yaw)
            let a = p * 0.12
            keyLightNode?.position = SCNVector3(Float(cos(a) * 1.6),
                                                Float(0.8 + sin(a) * 0.4),
                                                2.2)
        }
    }
}
