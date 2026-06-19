import SwiftUI

/// The always-on-screen circle. A small Siri orb that floats on top of
/// everything; click it to open the chat panel. Drag it (the window is movable
/// by background) to reposition. This is item #1 of the two-thing app.
struct FloatingOrb: View {
    @ObservedObject var model: AppModel
    var onTap: () -> Void

    @State private var phase: CGFloat = 0
    @State private var pulse: CGFloat = 0      // breathing pulse for "thought waiting"
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            // Gentle glow when she has a thought waiting — she feels "alive",
            // and you can tell at a glance she's been thinking of you.
            if model.hasThoughtWaiting {
                Circle()
                    .fill(RadialGradient(
                        colors: [Color.pink.opacity(0.45 * pulse), .clear],
                        center: .center, startRadius: 0,
                        endRadius: model.orbSize * 0.85))
                    .frame(width: model.orbSize * 1.7, height: model.orbSize * 1.7)
                    .blur(radius: 6)
                    .allowsHitTesting(false)
            }

            SiriOrb(amplitude: model.amplitude, phase: phase, tint: model.tint)
                .frame(width: model.orbSize, height: model.orbSize)
                .contentShape(Circle())
                .onTapGesture { onTap() }
        }
        .onReceive(timer) { _ in
            phase += 0.05 + model.amplitude * 0.30
            // slow, soft breathing pulse (0…1) for the waiting glow
            pulse = (sin(phase * 0.9) + 1) / 2
            model.syncPhase()
        }
        .help(model.hasThoughtWaiting ? "\(model.assistantName) has a thought for you"
                                      : "\(model.assistantName) — click to chat")
    }
}
