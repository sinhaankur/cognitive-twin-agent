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
            meter("smile", engine.readSmile, Color(red: 1, green: 0.85, blue: 0.45))
            Text("   ")
            meter("brow", engine.readBrow, Color(red: 0.94, green: 0.5, blue: 0.8))
            Text("   blink ")
                .foregroundStyle(Color(red: 0.55, green: 0.6, blue: 0.72))
            Text("\(Int(engine.readBlink))")
                .foregroundStyle(Color(red: 0.75, green: 0.82, blue: 0.95))
            Text("/m").foregroundStyle(Color(red: 0.55, green: 0.6, blue: 0.72))
        }
        .font(.system(size: 9, design: .monospaced))
    }

    /// One labelled meter. Filled segments carry the reading's colour; empty
    /// ones sit very dim so a resting face reads as calm, not broken/zeroed.
    private func meter(_ label: String, _ v: Double, _ hot: Color) -> some View {
        let n = Int((max(0, min(1, v)) * 5).rounded())
        let active = v > 0.5
        return HStack(spacing: 0) {
            Text("\(label) ")
                .foregroundStyle(Color(red: 0.55, green: 0.6, blue: 0.72))
            Text(String(repeating: "▮", count: n))
                .foregroundStyle(active ? hot : Color(red: 0.62, green: 0.68, blue: 0.82))
            Text(String(repeating: "▯", count: 5 - n))
                .foregroundStyle(Color(red: 0.34, green: 0.38, blue: 0.48).opacity(0.7))
        }
    }

    // ---- drawing -------------------------------------------------------------

    private func drawFace(g: inout GraphicsContext, size: CGSize, t: TimeInterval) {
        func at(_ d: FaceEngine.Dot) -> CGPoint {
            CGPoint(x: d.x * size.width, y: d.y * size.height)
        }
        // a soft focus behind the face — gives the frame depth and pulls the eye
        // to center instead of the dots floating in flat black
        if let mesh = Self.faceBounds(engine.dots) {
            let cx = (mesh.minX + mesh.maxX) / 2 * size.width
            let cy = (mesh.minY + mesh.maxY) / 2 * size.height
            let rad = max(mesh.width * size.width, mesh.height * size.height) * 0.95
            let focus = GraphicsContext.Shading.radialGradient(
                Gradient(colors: [Color(red: 0.32, green: 0.44, blue: 0.66).opacity(0.16),
                                  .clear]),
                center: CGPoint(x: cx, y: cy), startRadius: 0, endRadius: rad)
            g.fill(Path(ellipseIn: CGRect(x: cx - rad, y: cy - rad,
                                          width: rad * 2, height: rad * 2)),
                   with: focus)
        }
        let groups = Dictionary(grouping: engine.dots, by: \.group)
        for (group, dots) in groups where group >= 0 && dots.count > 2 {
            let pts = dots.map(at)
            let path = Self.smoothPath(pts, closed: dots[0].closes)
            let color = dots[0].color
            // a soft outer glow so each feature reads as a lit contour, not a hairline
            g.stroke(path, with: .color(color.opacity(0.22)),
                     style: StrokeStyle(lineWidth: 3.2, lineJoin: .round))
            // the thread — brighter + a touch thicker so the face actually reads
            g.stroke(path, with: .color(color.opacity(0.6)),
                     style: StrokeStyle(lineWidth: 1.3, lineJoin: .round))
            // expression glow: features re-stroke brighter as their reading rises
            let hot: Double = group >= 6 ? max(engine.readSmile, engine.readFrown)
                            : (group == 4 || group == 5) ? engine.readBrow : 0
            if hot > 0.25 {
                g.stroke(path, with: .color(color.opacity(hot * 0.85)),
                         style: StrokeStyle(lineWidth: 2.0, lineJoin: .round))
            }
            // a spark of light travels each thread (dash ring, phase = time)
            g.stroke(path, with: .color(.white.opacity(0.45)),
                     style: StrokeStyle(lineWidth: 1.1, lineCap: .round,
                                        dash: [2, 34],
                                        dashPhase: CGFloat(-t * 26).truncatingRemainder(dividingBy: 36)))
        }
        // the dots, each a point of light with a soft halo (brighter + larger halo)
        for d in engine.dots {
            let p = at(d)
            let halo = CGRect(x: p.x - d.r * 3.8, y: p.y - d.r * 3.8,
                              width: d.r * 7.6, height: d.r * 7.6)
            g.fill(Path(ellipseIn: halo), with: .color(d.color.opacity(d.alpha * 0.22)))
            let core = CGRect(x: p.x - d.r, y: p.y - d.r, width: d.r * 2, height: d.r * 2)
            g.fill(Path(ellipseIn: core), with: .color(d.color.opacity(min(1, d.alpha * 1.15))))
            // a crisp white pinpoint centre — reads as a live sensor point
            let pin = CGRect(x: p.x - d.r * 0.4, y: p.y - d.r * 0.4,
                             width: d.r * 0.8, height: d.r * 0.8)
            g.fill(Path(ellipseIn: pin), with: .color(.white.opacity(d.alpha * 0.8)))
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

    /// Normalized bounding box of the landmark cloud (0…1 space) — used to place
    /// the soft focus glow behind wherever the face actually is.
    private static func faceBounds(_ dots: [FaceEngine.Dot]) -> CGRect? {
        let real = dots.filter { $0.group >= 0 }
        guard let first = real.first else { return nil }
        var minX = first.x, maxX = first.x, minY = first.y, maxY = first.y
        for d in real {
            minX = min(minX, d.x); maxX = max(maxX, d.x)
            minY = min(minY, d.y); maxY = max(maxY, d.y)
        }
        return CGRect(x: minX, y: minY, width: maxX - minX, height: maxY - minY)
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
