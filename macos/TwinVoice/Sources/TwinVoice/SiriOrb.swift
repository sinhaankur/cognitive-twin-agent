import SwiftUI

/// The Siri visual: a glowing orb at rest that morphs into flowing, layered
/// sine-wave curves (siriwave-style) while listening or speaking.
///
/// `amplitude` (0…1) drives the morph: 0 = calm orb, higher = bigger, faster,
/// more wave-like. `phase` is advanced by the parent on a timer so the curves
/// flow. `tint` shifts with state (listening = blue, thinking = indigo,
/// speaking = teal/green).
struct SiriOrb: View {
    var amplitude: CGFloat        // 0…1
    var phase: CGFloat            // ever-increasing, drives the flow
    var tint: Color

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            ZStack {
                // --- soft glow halo ---
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [tint.opacity(0.55), tint.opacity(0.0)],
                            center: .center,
                            startRadius: 2,
                            endRadius: max(w, h) * 0.55
                        )
                    )
                    .scaleEffect(1.0 + amplitude * 0.25)
                    .blur(radius: 18)

                // --- the resting orb (fades out as amplitude rises) ---
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [tint.opacity(0.95), tint.opacity(0.35)],
                            center: .init(x: 0.4, y: 0.35),
                            startRadius: 1,
                            endRadius: min(w, h) * 0.5
                        )
                    )
                    .frame(width: min(w, h) * 0.42, height: min(w, h) * 0.42)
                    .opacity(Double(max(0, 0.9 - amplitude * 1.6)))
                    .scaleEffect(1.0 + amplitude * 0.1)

                // --- flowing wave layers (appear as amplitude rises) ---
                ForEach(0..<3, id: \.self) { i in
                    WaveCurve(
                        amplitude: amplitude * (1.0 - CGFloat(i) * 0.22),
                        phase: phase + CGFloat(i) * 1.3,
                        frequency: 1.6 + CGFloat(i) * 0.5
                    )
                    .stroke(
                        waveColor(i).opacity(Double(min(1, amplitude * 1.8))),
                        style: StrokeStyle(lineWidth: 3 - CGFloat(i) * 0.6, lineCap: .round)
                    )
                    .blendMode(.screen)
                }
            }
            .frame(width: w, height: h)
            .animation(.easeInOut(duration: 0.25), value: amplitude)
        }
    }

    private func waveColor(_ i: Int) -> Color {
        switch i {
        case 0: return tint
        case 1: return tint.opacity(0.8)
        default: return .white.opacity(0.7)
        }
    }
}

/// A single horizontal sine curve whose middle swells with amplitude — the
/// siriwave look: tall in the center, tapering to flat at the edges.
struct WaveCurve: Shape {
    var amplitude: CGFloat
    var phase: CGFloat
    var frequency: CGFloat

    // let SwiftUI animate phase/amplitude smoothly
    var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { AnimatablePair(amplitude, phase) }
        set { amplitude = newValue.first; phase = newValue.second }
    }

    func path(in rect: CGRect) -> Path {
        var p = Path()
        let midY = rect.midY
        let maxAmp = rect.height * 0.42 * amplitude
        let step: CGFloat = 2
        var x: CGFloat = 0
        p.move(to: CGPoint(x: 0, y: midY))
        while x <= rect.width {
            let t = x / rect.width                  // 0…1 across
            // bell envelope: 0 at edges, 1 in the middle (sin(pi*t))
            let envelope = sin(.pi * t)
            let y = midY + sin(t * frequency * 2 * .pi + phase) * maxAmp * envelope
            p.addLine(to: CGPoint(x: x, y: y))
            x += step
        }
        return p
    }
}
