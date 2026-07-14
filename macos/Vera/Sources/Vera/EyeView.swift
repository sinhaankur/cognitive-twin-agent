import SwiftUI

/// Her eye — the small always-visible preview window. Native Vision face
/// landmarks (FaceEngine), rendered as an instrument, not a debug view:
///   - every feature is a SMOOTH curve (midpoint quadratics through the
///     temporally-smoothed landmarks), closed for eyes and lips
///   - a faint spark of light travels the threads (the Face ID liveness cue)
///   - expressions light their own geometry: the mouth turns gold as a smile
///     grows, brows pink as they knit, eyes flash white on a blink — each
///     with a caption, because the dots should SAY what they read
///   - an instrument row shows the same readings as meters (smile ▮▮▮▯▯ …)
///   - no face → a quiet breathing reticle, not dead black
/// Same opt-in contract: camera only while this window exists; closing stops
/// and forgets (FaceEngine.stop + the native /api/presence/stop in VeraApp).
struct EyeView: View {
    @StateObject private var engine = FaceEngine()

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Color(red: 0.02, green: 0.024, blue: 0.04)
            TimelineView(.animation) { tl in
                let t = tl.date.timeIntervalSinceReferenceDate
                Canvas { g, size in
                    drawFrameTicks(g: &g, size: size)
                    if engine.dots.isEmpty {
                        drawReticle(g: &g, size: size, t: t)
                    } else {
                        drawFace(g: &g, size: size, t: t)
                    }
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                if engine.facePresent { meters }
                if !engine.reading.isEmpty {
                    Text(engine.reading)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(Color(red: 0.75, green: 0.8, blue: 0.9))
                }
                Text(engine.status)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(Color(red: 0.55, green: 0.6, blue: 0.7).opacity(0.75))
            }
            .padding(.leading, 10)
            .padding(.bottom, 8)
        }
        .onAppear { engine.start() }
        .onDisappear { engine.stop() }
    }

    // ---- the instrument row: the readings as meters -------------------------

    private static func bar(_ v: Double) -> String {
        let n = Int((max(0, min(1, v)) * 5).rounded())
        return String(repeating: "▮", count: n) + String(repeating: "▯", count: 5 - n)
    }

    private var meters: some View {
        HStack(spacing: 0) {
            Text("smile ").foregroundStyle(.secondary)
            Text(Self.bar(engine.readSmile))
                .foregroundStyle(engine.readSmile > 0.5
                                 ? Color(red: 1, green: 0.85, blue: 0.45) : .secondary)
            Text("  brow ").foregroundStyle(.secondary)
            Text(Self.bar(engine.readBrow))
                .foregroundStyle(engine.readBrow > 0.5
                                 ? Color(red: 0.94, green: 0.5, blue: 0.8) : .secondary)
            Text("  blink \(Int(engine.readBlink))/m")
                .foregroundStyle(.secondary)
        }
        .font(.system(size: 9, design: .monospaced))
    }

    // ---- drawing -------------------------------------------------------------

    private func drawFace(g: inout GraphicsContext, size: CGSize, t: TimeInterval) {
        func at(_ d: FaceEngine.Dot) -> CGPoint {
            CGPoint(x: d.x * size.width, y: d.y * size.height)
        }
        let groups = Dictionary(grouping: engine.dots, by: \.group)
        for (group, dots) in groups where group >= 0 && dots.count > 2 {
            let pts = dots.map(at)
            let path = Self.smoothPath(pts, closed: dots[0].closes)
            let color = dots[0].color
            // the thread
            g.stroke(path, with: .color(color.opacity(0.28)),
                     style: StrokeStyle(lineWidth: 0.8, lineJoin: .round))
            // expression glow: features re-stroke brighter as their reading rises
            let hot: Double = group >= 6 ? max(engine.readSmile, engine.readFrown)
                            : (group == 4 || group == 5) ? engine.readBrow : 0
            if hot > 0.25 {
                g.stroke(path, with: .color(color.opacity(hot * 0.7)),
                         style: StrokeStyle(lineWidth: 1.4, lineJoin: .round))
            }
            // a spark of light travels each thread (dash ring, phase = time)
            g.stroke(path, with: .color(.white.opacity(0.35)),
                     style: StrokeStyle(lineWidth: 1.0, lineCap: .round,
                                        dash: [2, 34],
                                        dashPhase: CGFloat(-t * 26).truncatingRemainder(dividingBy: 36)))
        }
        // the dots, each a point of light with a soft halo
        for d in engine.dots {
            let p = at(d)
            let halo = CGRect(x: p.x - d.r * 3.2, y: p.y - d.r * 3.2,
                              width: d.r * 6.4, height: d.r * 6.4)
            g.fill(Path(ellipseIn: halo), with: .color(d.color.opacity(d.alpha * 0.14)))
            let core = CGRect(x: p.x - d.r, y: p.y - d.r, width: d.r * 2, height: d.r * 2)
            g.fill(Path(ellipseIn: core), with: .color(d.color.opacity(d.alpha)))
        }
        for c in engine.captions {
            g.draw(Text(c.text)
                     .font(.system(size: 9, design: .monospaced))
                     .foregroundColor(c.color),
                   at: CGPoint(x: c.x * size.width, y: c.y * size.height))
        }
    }

    /// No face: a quiet breathing reticle — she's looking, not switched off.
    private func drawReticle(g: inout GraphicsContext, size: CGSize, t: TimeInterval) {
        let c = CGPoint(x: size.width / 2, y: size.height / 2)
        let breathe = 0.5 + 0.5 * sin(t * 1.6)
        let r = min(size.width, size.height) * (0.22 + 0.02 * breathe)
        let ring = Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2))
        g.stroke(ring, with: .color(Color(red: 0.49, green: 0.78, blue: 1)
                                        .opacity(0.10 + 0.10 * breathe)),
                 style: StrokeStyle(lineWidth: 1, dash: [3, 7],
                                    dashPhase: CGFloat(t * 6)))
    }

    /// Instrument corner ticks — the same frame language as the Mind.
    private func drawFrameTicks(g: inout GraphicsContext, size: CGSize) {
        let m: CGFloat = 8, l: CGFloat = 12
        var p = Path()
        for (x, y, sx, sy): (CGFloat, CGFloat, CGFloat, CGFloat) in
            [(m, m, 1, 1), (size.width - m, m, -1, 1),
             (m, size.height - m, 1, -1), (size.width - m, size.height - m, -1, -1)] {
            p.move(to: CGPoint(x: x + sx * l, y: y))
            p.addLine(to: CGPoint(x: x, y: y))
            p.addLine(to: CGPoint(x: x, y: y + sy * l))
        }
        g.stroke(p, with: .color(.white.opacity(0.14)), lineWidth: 1)
    }

    /// Midpoint-quadratic smoothing: a soft curve through jittery landmarks.
    private static func smoothPath(_ pts: [CGPoint], closed: Bool) -> Path {
        var path = Path()
        guard pts.count > 2 else { return path }
        func mid(_ a: CGPoint, _ b: CGPoint) -> CGPoint {
            CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
        }
        if closed {
            path.move(to: mid(pts[pts.count - 1], pts[0]))
            for i in 0..<pts.count {
                path.addQuadCurve(to: mid(pts[i], pts[(i + 1) % pts.count]),
                                  control: pts[i])
            }
            path.closeSubpath()
        } else {
            path.move(to: pts[0])
            for i in 1..<pts.count - 1 {
                path.addQuadCurve(to: mid(pts[i], pts[i + 1]), control: pts[i])
            }
            path.addLine(to: pts[pts.count - 1])
        }
        return path
    }
}
