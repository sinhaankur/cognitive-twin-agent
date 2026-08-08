import SwiftUI

/// Vera's emblem — an Ashokan GOLD ORB (the crowning sphere of the Lion Capital
/// of Sarnath). A warm sandstone-gold sphere: soft blobs swirl inside under
/// soft-light, an ember glows, a bright core pulses, a glass highlight sits
/// top-left, and a faint 24-spoke gold Ashoka Chakra turns over it. Circular,
/// gold, alive — NOT a Siri rainbow orb; the palette is Mauryan sandstone + ember.
///
/// Drop-in for `SiriOrb`: same interface (`amplitude`, `phase`, `tint`) so the
/// chat / menubar shell swaps the visual with no other change.
///   amplitude 0…1 — swells the core + breathing as she listens / speaks
///   phase          — ever-increasing; turns the chakra + swirls the interior
///   tint           — reserved (the orb owns its warm palette)
struct HexMark: View {
    var amplitude: CGFloat
    var phase: CGFloat
    var tint: Color = Color(red: 0.85, green: 0.70, blue: 0.40)

    // Mauryan sandstone palette.
    private let sand    = Color(red: 0.79, green: 0.60, blue: 0.42)
    private let sandLit = Color(red: 0.90, green: 0.78, blue: 0.60)
    private let plum    = Color(red: 0.29, green: 0.20, blue: 0.25)
    private let sky     = Color(red: 0.37, green: 0.46, blue: 0.44)
    private let ember   = Color(red: 0.91, green: 0.58, blue: 0.31)
    private let gold    = Color(red: 0.94, green: 0.86, blue: 0.65)

    var body: some View {
        GeometryReader { geo in
            let s = min(geo.size.width, geo.size.height)
            let breathe = 1.0 + sin(phase * 0.18) * 0.03 + amplitude * 0.06
            let corePulse = 0.85 + sin(phase * 0.5) * 0.12 + amplitude * 0.2

            ZStack {
                // Warm bloom behind the orb.
                Circle()
                    .fill(RadialGradient(colors: [ember.opacity(0.34), gold.opacity(0.12), .clear],
                                         center: .init(x: 0.5, y: 0.46), startRadius: 0, endRadius: s * 0.55))
                    .scaleEffect(breathe)

                // The sphere base gradient.
                Circle()
                    .fill(RadialGradient(colors: [sandLit, sand,
                                                  Color(red: 0.48, green: 0.36, blue: 0.31),
                                                  Color(red: 0.20, green: 0.15, blue: 0.12)],
                                         center: .init(x: 0.42, y: 0.34), startRadius: 0, endRadius: s * 0.55))

                // Swirling interior — soft-light blobs turning at the micro level.
                ZStack {
                    blob(sandLit, at: .init(x: 0.38, y: 0.40)).rotationEffect(.degrees(phase * 1.4))
                    blob(plum,    at: .init(x: 0.62, y: 0.44)).rotationEffect(.degrees(-phase * 1.0))
                    blob(sky,     at: .init(x: 0.50, y: 0.68)).rotationEffect(.degrees(phase * 1.7))
                }
                .blendMode(.softLight)

                // Ember glow.
                Circle()
                    .fill(RadialGradient(colors: [ember.opacity(0.85), .clear],
                                         center: .init(x: 0.48, y: 0.58), startRadius: 0, endRadius: s * 0.34))
                    .blendMode(.screen)
                    .rotationEffect(.degrees(-phase * 0.7))

                // Bright pulsing core.
                Circle()
                    .fill(RadialGradient(colors: [Color(red: 1, green: 0.96, blue: 0.88).opacity(0.92),
                                                  Color(red: 1, green: 0.85, blue: 0.63).opacity(0.55), .clear],
                                         center: .init(x: 0.46, y: 0.56), startRadius: 0, endRadius: s * 0.2))
                    .scaleEffect(corePulse)
                    .blendMode(.screen)

                // Faint 24-spoke gold Ashoka Chakra, slowly turning.
                ChakraShape(spokes: 24)
                    .stroke(gold.opacity(0.8), lineWidth: max(0.5, s * 0.006))
                    .overlay(Circle().stroke(gold.opacity(0.8), lineWidth: max(0.5, s * 0.007)).scaleEffect(0.72))
                    .padding(s * 0.14)
                    .blendMode(.overlay)
                    .rotationEffect(.degrees(phase * 0.4))

                // Glass highlight, top-left.
                Circle()
                    .fill(RadialGradient(colors: [Color.white.opacity(0.25), .clear],
                                         center: .init(x: 0.36, y: 0.24), startRadius: 0, endRadius: s * 0.28))
            }
            .frame(width: s, height: s)
            .clipShape(Circle())
            .scaleEffect(breathe)
        }
    }

    private func blob(_ c: Color, at p: UnitPoint) -> some View {
        Circle()
            .fill(RadialGradient(colors: [c, .clear], center: p, startRadius: 0, endRadius: 60))
            .blur(radius: 10)
    }
}

/// N spokes radiating from center to a rim — the Dharmachakra pattern.
private struct ChakraShape: Shape {
    let spokes: Int
    func path(in rect: CGRect) -> Path {
        let c = CGPoint(x: rect.midX, y: rect.midY)
        let r = min(rect.width, rect.height) * 0.5
        var p = Path()
        p.addEllipse(in: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2))
        for i in 0..<spokes {
            let a = 2 * Double.pi / Double(spokes) * Double(i)
            p.move(to: CGPoint(x: c.x + cos(a) * r * 0.16, y: c.y + sin(a) * r * 0.16))
            p.addLine(to: CGPoint(x: c.x + cos(a) * r * 0.94, y: c.y + sin(a) * r * 0.94))
        }
        return p
    }
}
