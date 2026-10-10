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
    var size: CGFloat

    var body: some View {
        SiriOrb(amplitude: model.orbSpringAmp,
                phase: model.orbPhase,
                tint: model.tint,
                brightness: model.brightness,
                portraitMesh: model.portraitMeshURL)
            .frame(width: size, height: size)
    }
}
