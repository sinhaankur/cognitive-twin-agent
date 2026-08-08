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

    /// Fraction of the day, 0…1 (0 = midnight, 0.5 = noon). Drives the day/night
    /// shift + the chakra's clock angle. The Ashoka Chakra is the WHEEL OF TIME —
    /// so the mark literally tracks the day: gold + high sun at noon, deep indigo
    /// gold at night, the wheel turning once per day like space and time.
    var dayFraction: CGFloat = HexMark.currentDayFraction()

    static func currentDayFraction() -> CGFloat {
        let c = Calendar.current.dateComponents([.hour, .minute, .second], from: Date())
        let secs = (c.hour ?? 0) * 3600 + (c.minute ?? 0) * 60 + (c.second ?? 0)
        return CGFloat(secs) / 86400.0
    }

    // How "day" is it? A smooth 0 (deep night) → 1 (full day) bell peaking at noon.
    private var daylight: CGFloat {
        // cos peaks at noon (dayFraction 0.5), troughs at midnight.
        let d = 0.5 - 0.5 * cos(dayFraction * 2 * .pi)   // 0 at midnight, 1 at noon
        return d
    }

    // PRIME GOLD by day; deep indigo-gold by night. Gold stays dominant; night
    // just cools + deepens it (the wheel of time turning to dusk).
    private func lerp(_ a: Color, _ b: Color, _ t: CGFloat) -> Color {
        let tt = max(0, min(1, t))
        return Color(.sRGB,
            red: comp(a, 0) + (comp(b, 0) - comp(a, 0)) * tt,
            green: comp(a, 1) + (comp(b, 1) - comp(a, 1)) * tt,
            blue: comp(a, 2) + (comp(b, 2) - comp(a, 2)) * tt)
    }
    private func comp(_ c: Color, _ i: Int) -> Double {
        #if canImport(AppKit)
        let n = NSColor(c).usingColorSpace(.sRGB) ?? .white
        return [Double(n.redComponent), Double(n.greenComponent), Double(n.blueComponent)][i]
        #else
        return 0.8
        #endif
    }

    // AUTHENTIC Ashoka palette (from india-fiscal-map's ASHOKA_DESIGN.md, sourced
    // from the real artefacts): buff Chunar SANDSTONE sphere + the true BLUE
    // Dharmachakra (Indian sky-blue, the flag's navy wheel) + gold-leaf accents
    // "used rarely". Not all-gold — that wasn't the real Ashoka color language.
    // Day = warm sunlit sandstone + bright blue wheel; night = cool stone + deep
    // indigo wheel (the wheel of time turning to dusk).
    private var sandLit: Color { lerp(Color(red: 0.72, green: 0.68, blue: 0.62), Color(red: 0.91, green: 0.87, blue: 0.78), daylight) } // #e9ddc7 lit
    private var sand:    Color { lerp(Color(red: 0.52, green: 0.48, blue: 0.44), Color(red: 0.86, green: 0.80, blue: 0.68), daylight) } // #dcccae
    private var ember:   Color { lerp(Color(red: 0.42, green: 0.40, blue: 0.46), Color(red: 0.66, green: 0.47, blue: 0.29), daylight) } // ochre
    private let goldLeaf = Color(red: 0.79, green: 0.635, blue: 0.153) // #c9a227 — rare gilding accent
    // The chakra blue, shifting day → night.
    private var chakraBlue: Color { lerp(Color(red: 0.14, green: 0.24, blue: 0.42), Color(red: 0.19, green: 0.47, blue: 0.75), daylight) } // #3078c0 → deep indigo

    var body: some View {
        GeometryReader { geo in
            let s = min(geo.size.width, geo.size.height)
            let breathe = 1.0 + sin(phase * 0.18) * 0.03 + amplitude * 0.06
            let corePulse = 0.9 + sin(phase * 0.5) * 0.1 + amplitude * 0.18

            ZStack {
                // Warm bloom halo behind the orb.
                Circle()
                    .fill(RadialGradient(colors: [goldLeaf.opacity(0.28), goldLeaf.opacity(0.10), .clear],
                                         center: .center, startRadius: 0, endRadius: s * 0.6))
                    .scaleEffect(breathe * 1.05)

                // Buff Chunar SANDSTONE sphere — sunlit stone by day, cool stone at
                // night, with the Mauryan mirror-polish sheen (bright top-left → deep
                // shaded rim). Warm, monumental — the pillar's crowning stone.
                Circle()
                    .fill(RadialGradient(
                        colors: [sandLit, sand,
                                 lerp(Color(red: 0.30, green: 0.28, blue: 0.34), Color(red: 0.55, green: 0.48, blue: 0.38), daylight),
                                 lerp(Color(red: 0.16, green: 0.15, blue: 0.20), Color(red: 0.33, green: 0.27, blue: 0.20), daylight)],
                        center: .init(x: 0.40, y: 0.36), startRadius: 0, endRadius: s * 0.62))

                // Swirling interior — soft warm light clearly turning (phase grows
                // ~3/s; these multipliers give a visible drift, not a static blob).
                ZStack {
                    blob(sandLit,          at: .init(x: 0.38, y: 0.40), r: s * 0.5).rotationEffect(.degrees(phase * 8))
                    blob(ember.opacity(0.9), at: .init(x: 0.60, y: 0.56), r: s * 0.45).rotationEffect(.degrees(-phase * 6))
                    blob(goldLeaf.opacity(0.7), at: .init(x: 0.50, y: 0.30), r: s * 0.4).rotationEffect(.degrees(phase * 11))
                }
                .blendMode(.screen)
                .opacity(0.7)

                // Glass highlight (top-left) — drawn BEFORE the chakra so the wheel
                // sits cleanly on top and never gets washed out.
                Circle()
                    .fill(RadialGradient(colors: [Color.white.opacity(0.22), .clear],
                                         center: .init(x: 0.34, y: 0.22), startRadius: 0, endRadius: s * 0.28))

                // A gentle warm center — NOT a blinding wash (that drowned the
                // chakra). Small + soft so the wheel's hub stays legible.
                Circle()
                    .fill(RadialGradient(colors: [Color(red: 1, green: 0.93, blue: 0.75).opacity(0.4),
                                                  .clear],
                                         center: .init(x: 0.46, y: 0.48), startRadius: 0, endRadius: s * 0.12))
                    .scaleEffect(corePulse)
                    .blendMode(.screen)

                // THE Ashoka Chakra — the true BLUE Dharmachakra (the flag's navy
                // wheel), the whole orb IS the wheel. Bold blue over warm stone =
                // the authentic Ashoka contrast, with a thin gold-leaf rim as the
                // "rare gilding". 24 spokes + inner ring + hub, drawn on top.
                ZStack {
                    // Gold-leaf outer rim (the rare gilding accent).
                    Circle()
                        .stroke(goldLeaf, lineWidth: max(1.2, s * 0.014))
                        .scaleEffect(0.95)
                    Circle()
                        .stroke(chakraBlue, lineWidth: max(1.2, s * 0.016))
                        .scaleEffect(0.90)
                    ChakraShape(spokes: 24)
                        .stroke(chakraBlue, lineWidth: max(0.9, s * 0.011))
                        .scaleEffect(0.90)
                    Circle()
                        .stroke(chakraBlue, lineWidth: max(0.9, s * 0.013))
                        .scaleEffect(0.27)
                    Circle().fill(chakraBlue).frame(width: s * 0.07, height: s * 0.07)
                }
                // THE WHEEL OF TIME: the chakra's angle IS the time of day — one
                // full 360° turn per day (dayFraction), so the top spoke points to
                // "now". A gentle live drift (phase) keeps it breathing between
                // seconds. Space and time, on Vera's face.
                .rotationEffect(.degrees(Double(dayFraction) * 360 + Double(phase) * 0.6))
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
