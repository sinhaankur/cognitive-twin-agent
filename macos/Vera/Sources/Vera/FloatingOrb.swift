import SwiftUI

/// The always-on-screen circle. A small Siri orb that floats on top of
/// everything; click it to open the chat panel. Drag it (the window is movable
/// by background) to reposition. This is item #1 of the two-thing app.
struct FloatingOrb: View {
    @ObservedObject var model: AppModel
    var onTap: () -> Void

    @State private var pressed = false         // click/tap highlight
    // Her visual form — the SAME switch LiveOrb reads, so the big floating orb you
    // actually look at honours it too (it used to hard-render the blob, ignoring
    // the Settings choice). "dots" = the point-cloud field; "siri" = old blob.
    @AppStorage("vera.orbForm") private var orbForm: String = "dots"
    // Animation state (phase, spring-tracked amplitude, breathing pulse) now comes
    // from the ONE shared driver on AppModel — no per-view 60fps timer. This orb
    // just READS model.orbPhase / orbSpringAmp / orbPulse, so it rests exactly
    // when she rests.

    var body: some View {
        ZStack {
            // Gentle glow when she has a thought waiting — she feels "alive",
            // and you can tell at a glance she's been thinking of you.
            if model.hasThoughtWaiting {
                Circle()
                    .fill(RadialGradient(
                        colors: [Color.pink.opacity(0.45 * model.orbPulse), .clear],
                        center: .center, startRadius: 0,
                        endRadius: model.orbSize * 0.85))
                    .frame(width: model.orbSize * 1.7, height: model.orbSize * 1.7)
                    .blur(radius: 6)
                    .allowsHitTesting(false)
            }

            ZStack {
                if orbForm == "siri" {
                    SiriOrb(amplitude: model.orbSpringAmp, phase: model.orbPhase,
                            tint: model.tint, brightness: model.brightness)
                } else {
                    DottedOrb(amplitude: model.orbSpringAmp, phase: model.orbPhase,
                              tint: model.tint)
                }
                // press highlight: a bright ring that flashes on click
                Circle()
                    .strokeBorder(Color.white.opacity(pressed ? 0.9 : 0), lineWidth: 3)
                    .blur(radius: 1)
            }
            .frame(width: model.orbSize, height: model.orbSize)
            .brightness(pressed ? 0.12 : 0)            // briefly brighten on press
            .scaleEffect(pressed ? 0.92 : 1.0)         // satisfying "push" feel
            .animation(.spring(response: 0.25, dampingFraction: 0.6), value: pressed)
            .contentShape(Circle())
            .onTapGesture { flash(); onTap() }
        }
        // Fill the (larger) window with a transparent canvas so the glow can fade
        // out before the edge — no background, no square.
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
        .help(model.hasThoughtWaiting ? "\(model.assistantName) has a thought for you"
                                      : "\(model.assistantName) — click to chat")
    }

    /// Brief press highlight on click — the orb brightens, rings, and springs.
    private func flash() {
        pressed = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) { pressed = false }
    }
}
