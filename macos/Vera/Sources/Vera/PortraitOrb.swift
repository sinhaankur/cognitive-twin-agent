import SwiftUI
import SceneKit

/// A loved one, held in 3D inside the orb — the "living photo."
///
/// This is a sub-state of the orb, not a replacement: a Blender-built USDZ relief
/// (their real photo, displaced by AI-estimated depth — no invented geometry)
/// rendered live in SceneKit with a slow parallax turn and a drifting key light,
/// so the face feels present rather than flat.
///
/// HONESTY / QUALITY RULES, matching the rest of Vera:
///   • Opt-in only. Nothing here runs unless the "See a loved one in 3D" switch
///     is on AND a real mesh exists on this Mac.
///   • Broken must never animate. If there is no USDZ yet, this view is
///     `EmptyView` — the orb renders exactly as it always has, not one pixel
///     different. A face only ever appears when it is real.
///   • Local only. The mesh is a file on this Mac (built by the portrait
///     pipeline); nothing is fetched, nothing is sent.
struct PortraitOrb: View {
    /// Path to the USDZ face relief, or nil if none has been built.
    let meshURL: URL?
    /// Ever-increasing; shared with the orb so the turn stays in sync with the swirl.
    var phase: CGFloat

    var body: some View {
        if let url = meshURL, FileManager.default.fileExists(atPath: url.path) {
            PortraitSceneView(meshURL: url, phase: phase)
                .clipShape(Circle())          // stay inside the orb's mask
                .allowsHitTesting(false)      // the orb still owns taps
        } else {
            EmptyView()                       // no face yet → orb is untouched
        }
    }
}

/// The SceneKit host: loads the USDZ once, then each frame nudges the face's
/// yaw (parallax turn) and the key light's angle (light drift) from `phase`.
private struct PortraitSceneView: NSViewRepresentable {
    let meshURL: URL
    var phase: CGFloat

    func makeNSView(context: Context) -> SCNView {
        let view = SCNView()
        view.backgroundColor = .clear
        view.antialiasingMode = .multisampling4X
        view.rendersContinuously = true
        view.scene = context.coordinator.buildScene(from: meshURL)
        return view
    }

    func updateNSView(_ view: SCNView, context: Context) {
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

            // the imported face (first geometry-bearing node)
            let face = scene.rootNode.childNodes.first { $0.geometry != nil }
                ?? scene.rootNode
            // frame it: center at origin, sensible scale
            let (minB, maxB) = face.boundingBox
            let center = SCNVector3((minB.x + maxB.x) / 2,
                                    (minB.y + maxB.y) / 2,
                                    (minB.z + maxB.z) / 2)
            face.pivot = SCNMatrix4MakeTranslation(center.x, center.y, center.z)
            faceNode = face

            // camera, slightly back, looking at the face
            let cam = SCNNode()
            cam.camera = SCNCamera()
            cam.camera?.fieldOfView = 28
            cam.position = SCNVector3(0, 0, 2.6)
            scene.rootNode.addChildNode(cam)

            // a soft fill so shadows never crush to black (relief stays readable)
            let fill = SCNNode()
            fill.light = SCNLight()
            fill.light?.type = .ambient
            fill.light?.intensity = 320
            scene.rootNode.addChildNode(fill)

            // the drifting key light — this is what makes the face feel alive
            let key = SCNNode()
            key.light = SCNLight()
            key.light?.type = .omni
            key.light?.intensity = 900
            key.position = SCNVector3(1.4, 1.0, 2.2)
            scene.rootNode.addChildNode(key)
            keyLightNode = key

            return scene
        }

        /// Slow parallax turn + light drift, driven by the orb's phase so the two
        /// motions never fight. Deliberately gentle — a few degrees, respectful.
        func update(phase: CGFloat) {
            let p = Double(phase)
            // face yaw: ±7° sway, no full spin — a portrait, not a turntable
            let yaw = sin(p * 0.18) * (7.0 * .pi / 180.0)
            faceNode?.eulerAngles.y = CGFloat(yaw)
            // key light orbits a small arc so highlights travel across the face
            let a = p * 0.12
            keyLightNode?.position = SCNVector3(cos(a) * 1.6,
                                                0.8 + sin(a) * 0.4,
                                                2.2)
        }
    }
}
