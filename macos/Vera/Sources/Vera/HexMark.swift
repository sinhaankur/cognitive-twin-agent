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

    var body: some View {
        GeometryReader { geo in
            let s = min(geo.size.width, geo.size.height)
            let breathe = 1.0 + sin(phase * 0.6) * 0.03 + amplitude * 0.10

            ZStack {
                // Soft inner glow that breathes.
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [tint.opacity(0.55 + amplitude * 0.4),
                                     tint.opacity(0.10), .clear],
                            center: .center, startRadius: 0, endRadius: s * 0.42
                        )
                    )
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
