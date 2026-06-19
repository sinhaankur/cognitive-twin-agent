import SwiftUI

/// The modern macOS Siri visual: a soft, multicolor iridescent orb. Several
/// blurred color blobs (pink / purple / blue / cyan / orange) swirl inside a
/// circular mask over a bright bloom, with a glassy highlight on top. It breathes
/// at rest and intensifies — brighter, faster swirl, bigger bloom — as `amplitude`
/// rises (listening / speaking).
///
///   amplitude  0…1, drives bloom + swirl speed + scale
///   phase      ever-increasing; rotates the blobs so the colors flow
///   tint       a subtle state bias (listening cooler, speaking warmer) layered
///              on top of the rainbow, so state still reads without losing "Siri".
struct SiriOrb: View {
    var amplitude: CGFloat
    var phase: CGFloat
    var tint: Color

    // The Siri palette — saturated, luminous.
    private let blobs: [Color] = [
        Color(red: 1.00, green: 0.27, blue: 0.55),   // pink
        Color(red: 0.62, green: 0.30, blue: 1.00),   // purple
        Color(red: 0.20, green: 0.52, blue: 1.00),   // blue
        Color(red: 0.18, green: 0.85, blue: 0.95),   // cyan
        Color(red: 1.00, green: 0.62, blue: 0.20),   // orange
    ]

    var body: some View {
        GeometryReader { geo in
            let s = min(geo.size.width, geo.size.height)
            let r = s * 0.5
            let breathe = 1.0 + sin(phase * 0.6) * 0.02 + amplitude * 0.12

            ZStack {
                // --- outer glow / bloom (spills beyond the sphere) ---
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                .white.opacity(0.25 + amplitude * 0.4),
                                blobs[1].opacity(0.35 + amplitude * 0.3),
                                .clear,
                            ],
                            center: .center, startRadius: 0, endRadius: r * 1.15
                        )
                    )
                    .blur(radius: 22)
                    .scaleEffect(1.05 + amplitude * 0.18)

                // --- the orb body: swirling color blobs inside a circle ---
                ZStack {
                    // dark base so colors read as luminous, like the real orb
                    Circle().fill(Color.black.opacity(0.55))

                    ForEach(blobs.indices, id: \.self) { i in
                        let a = phase * (0.4 + CGFloat(i) * 0.06) + CGFloat(i) * (.pi * 2 / CGFloat(blobs.count))
                        // orbit radius pulses with amplitude → "energetic" when active
                        let orbit = r * (0.18 + 0.10 * sin(phase * 0.5 + CGFloat(i)))
                            + r * amplitude * 0.12
                        Circle()
                            .fill(blobs[i])
                            .frame(width: r * 1.05, height: r * 1.05)
                            .offset(x: cos(a) * orbit, y: sin(a) * orbit)
                            .blendMode(.plusLighter)
                            .opacity(0.85)
                    }

                    // central white-hot core (grows when speaking/listening)
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [.white.opacity(0.9), .white.opacity(0.0)],
                                center: .center, startRadius: 0, endRadius: r * (0.35 + amplitude * 0.3)
                            )
                        )
                        .blendMode(.plusLighter)

                    // subtle state tint wash (keeps listening/speaking legible)
                    Circle()
                        .fill(tint.opacity(0.18))
                        .blendMode(.softLight)
                }
                .frame(width: s, height: s)
                .blur(radius: r * 0.10)               // melt the blobs together
                .clipShape(Circle())

                // --- glassy specular highlight (top-left) ---
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [.white.opacity(0.5), .clear],
                            center: .init(x: 0.34, y: 0.30),
                            startRadius: 0, endRadius: r * 0.5
                        )
                    )
                    .blendMode(.screen)
                    .clipShape(Circle())

                // --- crisp rim ---
                Circle()
                    .strokeBorder(
                        LinearGradient(colors: [.white.opacity(0.35), .white.opacity(0.05)],
                                       startPoint: .topLeading, endPoint: .bottomTrailing),
                        lineWidth: 1
                    )
            }
            .frame(width: s, height: s)
            .scaleEffect(breathe)
            .animation(.easeInOut(duration: 0.25), value: amplitude)
        }
    }
}
