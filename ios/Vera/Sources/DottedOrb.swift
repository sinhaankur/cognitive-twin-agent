import SwiftUI

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

    // The sphere of unit points, built once (Fibonacci distribution → even).
    private static let points: [SIMD3<Double>] = {
        let n = 260
        var pts: [SIMD3<Double>] = []
        let golden = Double.pi * (3 - (5.0).squareRoot())
        for i in 0..<n {
            let y = 1 - (Double(i) / Double(n - 1)) * 2
            let r = (1 - y * y).squareRoot()
            let t = golden * Double(i)
            pts.append(SIMD3(cos(t) * r, y, sin(t) * r))
        }
        return pts
    }()

    var body: some View {
        Canvas { ctx, size in
            let s = min(size.width, size.height)
            let cx = size.width / 2, cy = size.height / 2
            let R = s * 0.40
            let p = Double(phase)
            let amp = Double(min(max(amplitude, 0), 1))

            // breathe + voice swell
            let breathe = 1.0 + sin(p * 0.6) * 0.02 + amp * 0.22

            // rotation (around Y then a fixed tilt around X so it reads 3D)
            let ry = p * 0.25
            let rx = 0.32
            let cosY = cos(ry), sinY = sin(ry)
            let cosX = cos(rx), sinX = sin(rx)

            // soft tinted bloom behind the sphere
            let bloom = Path(ellipseIn: CGRect(x: cx - R * 1.5, y: cy - R * 1.5,
                                               width: R * 3, height: R * 3))
            ctx.fill(bloom, with: .radialGradient(
                Gradient(colors: [tint.opacity(0.18 + amp * 0.18), tint.opacity(0)]),
                center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: R * 1.5))

            for pt in Self.points {
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
                let dotR = CGFloat(0.6 + depth * 1.6)
                let alpha = CGFloat(0.16 + depth * 0.78)

                let dot = Path(ellipseIn: CGRect(x: px - dotR, y: py - dotR,
                                                 width: dotR * 2, height: dotR * 2))
                // near dots take the tint; far dots fade toward it too, dimmer.
                ctx.fill(dot, with: .color(tint.opacity(alpha)))
            }
        }
        .drawingGroup() // render on the GPU — smooth at 60fps
    }
}
