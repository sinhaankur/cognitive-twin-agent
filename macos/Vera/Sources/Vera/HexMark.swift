import SwiftUI

/// Vera's emblem — a faceted hexagon enclosing the 24-spoke Ashoka Chakra
/// (Dharmachakra), drawn in the twin's amber accent. Deliberately NOT a
/// Siri-style orb: the geometry echoes Ashokan / Mauryan design — the spoked
/// discipline of the Sarnath capital, framed by a hexagon rather than a wheel.
///
/// Drop-in for `SiriOrb`: same interface (`amplitude`, `phase`, `tint`) so the
/// chat/menubar shell can swap the visual without other changes.
///   amplitude 0…1 — breathes the inner glow (listening / speaking)
///   phase          — ever-increasing; slowly turns the chakra
///   tint           — state bias (listening cooler, speaking warmer)
struct HexMark: View {
    var amplitude: CGFloat
    var phase: CGFloat
    var tint: Color = Color(red: 0.81, green: 0.60, blue: 0.17) // ~#cf9a2c amber

    // A warm, amber-led palette for the living bloom behind the geometry —
    // gold → amber → rose → deep-orange. Distinct from Siri's cool rainbow, so
    // the mark reads as VERA's (Ashokan warmth), not a Siri copy.
    private let blobs: [Color] = [
        Color(red: 1.00, green: 0.80, blue: 0.35),  // gold
        Color(red: 0.95, green: 0.55, blue: 0.18),  // amber
        Color(red: 0.92, green: 0.38, blue: 0.30),  // rose-orange
        Color(red: 0.78, green: 0.30, blue: 0.45),  // deep rose
    ]

    var body: some View {
        GeometryReader { geo in
            let s = min(geo.size.width, geo.size.height)
            let breathe = 1.0 + sin(phase * 0.6) * 0.03 + amplitude * 0.10

            ZStack {
                // --- LIVING BACKGROUND: colored blobs swirl behind the geometry,
                //     clipped to the hexagon, so the mark feels alive like the Siri
                //     orb did — without becoming an orb. Warm amber-led palette. ---
                ZStack {
                    ForEach(0..<blobs.count, id: \.self) { i in
                        let a = Double(phase) * (0.35 + Double(i) * 0.08) + Double(i) * 2.4
                        let orbit = s * (0.11 + 0.03 * Double(i)) * (1 + amplitude * 0.5)
                        Circle()
                            .fill(blobs[i])
                            .frame(width: s * (0.42 + amplitude * 0.18),
                                   height: s * (0.42 + amplitude * 0.18))
                            .offset(x: CGFloat(cos(a)) * orbit,
                                    y: CGFloat(sin(a * 1.13)) * orbit)
                            .blur(radius: s * 0.09)
                            .opacity(0.55 + amplitude * 0.35)
                    }
                }
                .scaleEffect(breathe)
                .clipShape(HexShape())
                .blendMode(.plusLighter)

                // Bright breathing core bloom.
                Circle()
                    .fill(RadialGradient(
                        colors: [tint.opacity(0.7 + amplitude * 0.3),
                                 tint.opacity(0.12), .clear],
                        center: .center, startRadius: 0, endRadius: s * 0.34))
                    .scaleEffect(breathe)

                // Hexagon frame (pointy-top).
                HexShape()
                    .stroke(tint.opacity(0.9), style: StrokeStyle(lineWidth: s * 0.016, lineJoin: .round))

                // Inset hexagon.
                HexShape()
                    .stroke(tint.opacity(0.5), lineWidth: s * 0.010)
                    .scaleEffect(0.52)

                // The 24-spoke Ashoka Chakra, slowly turning with phase.
                ChakraShape(spokes: 24)
                    .stroke(tint.opacity(0.55), lineWidth: s * 0.006)
                    .rotationEffect(.degrees(Double(phase) * 3))

                // Chakra rim.
                Circle()
                    .stroke(tint.opacity(0.5), lineWidth: s * 0.008)
                    .scaleEffect(0.68)

                // Center hub.
                Circle().fill(tint).frame(width: s * 0.06, height: s * 0.06)
                Circle().stroke(tint.opacity(0.5), lineWidth: s * 0.008)
                    .frame(width: s * 0.11, height: s * 0.11)
            }
            .frame(width: s, height: s)
        }
    }
}

/// A pointy-top regular hexagon inscribed in the frame.
private struct HexShape: Shape {
    func path(in rect: CGRect) -> Path {
        let c = CGPoint(x: rect.midX, y: rect.midY)
        let r = min(rect.width, rect.height) * 0.5
        var p = Path()
        for i in 0..<6 {
            let a = Double.pi / 3 * Double(i) - Double.pi / 6
            let pt = CGPoint(x: c.x + r * cos(a), y: c.y + r * sin(a))
            if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
        }
        p.closeSubpath()
        return p
    }
}

/// N spokes radiating from the center to a rim — the Dharmachakra pattern.
private struct ChakraShape: Shape {
    let spokes: Int
    func path(in rect: CGRect) -> Path {
        let c = CGPoint(x: rect.midX, y: rect.midY)
        let r = min(rect.width, rect.height) * 0.34
        var p = Path()
        for i in 0..<spokes {
            let a = 2 * Double.pi / Double(spokes) * Double(i)
            p.move(to: c)
            p.addLine(to: CGPoint(x: c.x + r * cos(a), y: c.y + r * sin(a)))
        }
        return p
    }
}
