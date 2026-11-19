import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

/// DottedOrb — Vera as a point-cloud: dots arranged on a sphere, drawn in a
/// SwiftUI `Canvas`, rotating and pulsing so the orb reads as a living thing
/// that *says what she's doing*. The native twin of the website's dotted orb.
///
/// Inspired by the open-source "Thinking Orbs" concept (Jakub Antalik) — the
/// idea that each state deserves its own distinct orb. This is our own
/// implementation: a Fibonacci-sphere of points, depth-shaded (near dots are
/// bigger/brighter), tinted by the current state colour, pulsing with the voice.
///
/// Drop-in for SiriOrb — same props:
///   amplitude  0…1 voice loudness (pulses the cloud)
///   phase      ever-increasing; drives rotation
///   tint       the state colour (listening cooler, speaking warmer, …)
struct DottedOrb: View {
    var amplitude: CGFloat
    var phase: CGFloat
    var tint: Color

    // Fibonacci spheres at a few densities — a SMALL orb (chat header, 32pt) needs
    // FEWER points or the dots pack into a solid disc (the "flat blob" bug); a big
    // orb can carry more. We pick the right one for the frame in body.
    private static func sphere(_ n: Int) -> [SIMD3<Double>] {
        var pts: [SIMD3<Double>] = []
        let golden = Double.pi * (3 - (5.0).squareRoot())
        for i in 0..<n {
            let y = 1 - (Double(i) / Double(n - 1)) * 2
            let r = (1 - y * y).squareRoot()
            let t = golden * Double(i)
            pts.append(SIMD3(cos(t) * r, y, sin(t) * r))
        }
        return pts
    }
    private static let pointsSmall = sphere(70)    // ≤ 40pt orbs (chat header)
    private static let pointsMid   = sphere(150)   // ≤ 90pt
    private static let pointsLarge = sphere(260)   // big (main window / empty state)

    var body: some View {
        Canvas { ctx, size in
            let s = min(size.width, size.height)
            let cx = size.width / 2, cy = size.height / 2
            let R = s * 0.40
            let p = Double(phase)
            let amp = Double(min(max(amplitude, 0), 1))

            // Density + dot size scale with the FRAME — a 32pt header orb needs
            // fewer, smaller dots or 260 points pack into a solid disc (the flat
            // blob). The dot radius is a fraction of R so dots stay distinct at
            // every size.
            let points: [SIMD3<Double>]
            if s <= 42 { points = Self.pointsSmall }
            else if s <= 96 { points = Self.pointsMid }
            else { points = Self.pointsLarge }
            let dotBase = max(0.5, R * 0.055)          // near-dot radius, size-relative
            let dotSpread = max(0.6, R * 0.075)

            // breathe + voice swell — a calm, organic breath (two slow sines so it
            // never feels mechanical) plus a soft voice-driven swell.
            let breathe = 1.0 + sin(p * 0.6) * 0.014 + sin(p * 0.23 + 1.3) * 0.008 + amp * 0.16

            // rotation — a quiet primary turn plus a very slight secondary tilt
            // drift, so the cloud feels alive (gently tumbling), not spinning on a
            // fixed axis like a turntable.
            let ry = p * 0.16
            let rx = 0.30 + sin(p * 0.11) * 0.06
            let cosY = cos(ry), sinY = sin(ry)
            let cosX = cos(rx), sinX = sin(rx)

            // A soft two-stop bloom behind the sphere — a brighter inner core
            // fading to nothing. Quiet halo, premium, never a loud flare.
            let bloom = Path(ellipseIn: CGRect(x: cx - R * 1.45, y: cy - R * 1.45,
                                               width: R * 2.9, height: R * 2.9))
            ctx.fill(bloom, with: .radialGradient(
                Gradient(stops: [
                    .init(color: tint.opacity(0.16 + amp * 0.14), location: 0.0),
                    .init(color: tint.opacity(0.06), location: 0.45),
                    .init(color: tint.opacity(0.0), location: 1.0),
                ]),
                center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: R * 1.45))

            // A lighter tint for the lit, front-facing dots so the sphere has a
            // sense of light hitting it — front reads bright, back recedes cool.
            let lit = Color(white: 1.0).opacity(1.0)   // highlight blended per-dot below

            for pt in points {
                // rotate
                var x1 = pt.x * cosY - pt.z * sinY
                let z1 = pt.x * sinY + pt.z * cosY
                var y1 = pt.y * cosX - z1 * sinX
                var z2 = pt.y * sinX + z1 * cosX

                let rad = breathe
                x1 *= rad; y1 *= rad; z2 *= rad

                let px = cx + CGFloat(x1) * R
                let py = cy + CGFloat(y1) * R
                let depth = (z2 + 1) / 2            // 0 back → 1 front
                let dotR = dotBase + CGFloat(depth) * dotSpread
                // back dots dimmer so the sphere reads 3D, but not so opaque they
                // merge into a fill.
                let alpha = CGFloat(0.10 + depth * 0.66)

                // front dots pick up a touch of highlight (a soft top-light), so the
                // orb looks lit and dimensional rather than a flat field of one colour.
                let highlight = max(0, (depth - 0.55)) * 0.9
                let dotColor = tint.opacity(alpha).blended(with: lit, amount: highlight)

                let dot = Path(ellipseIn: CGRect(x: px - dotR, y: py - dotR,
                                                 width: dotR * 2, height: dotR * 2))
                ctx.fill(dot, with: .color(dotColor))
            }
        }
        .drawingGroup() // render on the GPU — smooth at 60fps
    }
}

private extension Color {
    /// Blend this colour toward `other` by `amount` (0…1), preserving this
    /// colour's alpha. Used to add a soft highlight to the orb's front dots.
    func blended(with other: Color, amount: Double) -> Color {
        let a = max(0, min(1, amount))
        guard a > 0 else { return self }
        #if canImport(AppKit)
        let c1 = NSColor(self).usingColorSpace(.sRGB) ?? NSColor(self)
        let c2 = NSColor(other).usingColorSpace(.sRGB) ?? NSColor(other)
        let r = c1.redComponent   + (c2.redComponent   - c1.redComponent)   * a
        let g = c1.greenComponent + (c2.greenComponent - c1.greenComponent) * a
        let b = c1.blueComponent  + (c2.blueComponent  - c1.blueComponent)  * a
        return Color(.sRGB, red: r, green: g, blue: b, opacity: c1.alphaComponent)
        #else
        return self
        #endif
    }
}
