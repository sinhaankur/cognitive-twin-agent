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
            let corePulse = 0.9 + sin(phase * 0.5) * 0.1 + amplitude * 0.18

            ZStack {
                // Warm bloom halo behind the orb.
                Circle()
                    .fill(RadialGradient(colors: [ember.opacity(0.45), gold.opacity(0.16), .clear],
                                         center: .center, startRadius: 0, endRadius: s * 0.6))
                    .scaleEffect(breathe * 1.05)

                // Luminous gold sphere base — warm all the way, only a gentle
                // deepening at the rim (no muddy black bottom).
                Circle()
                    .fill(RadialGradient(
                        colors: [sandLit, sand,
                                 Color(red: 0.62, green: 0.44, blue: 0.30),
                                 Color(red: 0.40, green: 0.27, blue: 0.20)],
                        center: .init(x: 0.40, y: 0.36), startRadius: 0, endRadius: s * 0.62))

                // Swirling interior — soft warm light clearly turning (phase grows
                // ~3/s; these multipliers give a visible drift, not a static blob).
                ZStack {
                    blob(sandLit,          at: .init(x: 0.38, y: 0.40), r: s * 0.5).rotationEffect(.degrees(phase * 8))
                    blob(ember.opacity(0.9), at: .init(x: 0.60, y: 0.56), r: s * 0.45).rotationEffect(.degrees(-phase * 6))
                    blob(gold,             at: .init(x: 0.50, y: 0.30), r: s * 0.4).rotationEffect(.degrees(phase * 11))
                }
                .blendMode(.screen)
                .opacity(0.7)

                // Bright pulsing core — the heart of the orb.
                Circle()
                    .fill(RadialGradient(colors: [Color(red: 1, green: 0.97, blue: 0.90),
                                                  Color(red: 1, green: 0.86, blue: 0.62).opacity(0.6), .clear],
                                         center: .init(x: 0.46, y: 0.50), startRadius: 0, endRadius: s * 0.26))
                    .scaleEffect(corePulse)
                    .blendMode(.screen)

                // Faint 24-spoke gold Ashoka Chakra — a DELICATE overlay, not a
                // wire mesh: thin, low-opacity, sitting lightly over the glow.
                ChakraShape(spokes: 24)
                    .stroke(gold.opacity(0.4), lineWidth: max(0.4, s * 0.004))
                    .overlay(Circle().stroke(gold.opacity(0.45), lineWidth: max(0.4, s * 0.005)).scaleEffect(0.7))
                    .padding(s * 0.16)
                    // Clearly turning: phase grows ~3/s, ×3 ≈ 9°/s — a calm,
                    // visible rotation (the reference's "chakra keeps working").
                    .rotationEffect(.degrees(phase * 3))
                    .opacity(0.85)

                // Glass highlight, top-left.
                Circle()
                    .fill(RadialGradient(colors: [Color.white.opacity(0.35), .clear],
                                         center: .init(x: 0.34, y: 0.22), startRadius: 0, endRadius: s * 0.3))
            }
            .frame(width: s, height: s)
            .clipShape(Circle())
            .scaleEffect(breathe)
        }
    }

    private func blob(_ c: Color, at p: UnitPoint, r: CGFloat) -> some View {
        Circle()
            .fill(RadialGradient(colors: [c, .clear], center: p, startRadius: 0, endRadius: r))
            .blur(radius: 8)
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
