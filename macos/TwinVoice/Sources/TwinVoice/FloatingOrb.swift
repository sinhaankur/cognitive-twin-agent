import SwiftUI

/// The always-on-screen circle. A small Siri orb that floats on top of
/// everything; click it to open the chat panel. Drag it (the window is movable
/// by background) to reposition. This is item #1 of the two-thing app.
struct FloatingOrb: View {
    @ObservedObject var model: AppModel
    var onTap: () -> Void

    @State private var phase: CGFloat = 0
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        SiriOrb(amplitude: model.amplitude, phase: phase, tint: model.tint)
            .frame(width: model.orbSize, height: model.orbSize)
            .contentShape(Circle())
            .onTapGesture { onTap() }
            .onReceive(timer) { _ in
                phase += 0.05 + model.amplitude * 0.30
                model.syncPhase()
            }
            .help("Twin — click to chat")
    }
}
