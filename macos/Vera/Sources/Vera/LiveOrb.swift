import SwiftUI

/// A self-contained, animating orb that reads the shared animation state
/// (`orbPhase` / `orbSpringAmp`) off the model ITSELF.
///
/// Why this exists: the orb's phase changes ~60×/sec while she's animating. If a
/// big view (the chat panel, the main window) reads `model.orbPhase` directly in
/// its own body, SwiftUI re-evaluates that WHOLE body — including its `TextField`
/// / `FocusState` — on every frame. That continuous re-render of a large tree
/// (not the drawing itself) was the app's real idle/active CPU cost. By giving
/// the orb its own small `@ObservedObject` view, only THIS tiny view re-renders
/// when the phase ticks; the panel around it stays still. Isolation, not a timer
/// tweak, is the fix.
struct LiveOrb: View {
    @ObservedObject var model: AppModel
    // Observe the ANIMATION driver directly — so a 24fps phase tick redraws THIS
    // tiny orb view and nothing else (model is observed too, but it only changes
    // on real state transitions, not every frame).
    @ObservedObject var orb: OrbDriver
    var size: CGFloat
    // Vera's visual form, switchable + remembered. "dots" = the point-cloud orb
    // (matches the website); "siri" = the original iridescent blob. Defaults to
    // the dotted field; flip back in Settings via @AppStorage("vera.orbForm").
    @AppStorage("vera.orbForm") private var orbForm: String = "dots"

    init(model: AppModel, size: CGFloat) {
        self.model = model
        self.orb = model.orb
        self.size = size
    }

    var body: some View {
        Group {
            if orbForm == "siri" {
                SiriOrb(amplitude: orb.springAmp,
                        phase: orb.phase,
                        tint: model.tint,
                        brightness: model.brightness,
                        portraitMesh: model.portraitMeshURL)
            } else {
                DottedOrb(amplitude: orb.springAmp,
                          phase: orb.phase,
                          tint: model.tint)
            }
        }
        .frame(width: size, height: size)
    }
}
