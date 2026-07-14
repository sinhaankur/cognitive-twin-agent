import SwiftUI

/// Her eye — the small always-visible preview window. Native now: Apple's
/// Vision face landmarks (FaceEngine) instead of the /eye page's optical flow.
/// The preview shows no video, only the dots — and the dots speak: the mouth
/// lights up captioned "smile", the brows when they knit, the eyes on a blink.
/// Same opt-in, on-device contract: camera only while this window exists;
/// closing it stops the camera and forgets (FaceEngine.stop + the native
/// /api/presence/stop in VeraApp).
struct EyeView: View {
    @StateObject private var engine = FaceEngine()

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            Color(red: 0.02, green: 0.024, blue: 0.04)
            Canvas { g, size in
                func at(_ d: FaceEngine.Dot) -> CGPoint {
                    CGPoint(x: d.x * size.width, y: d.y * size.height)
                }
                // constellation lines first — each feature drawn as one thin
                // thread (closed for eyes and lips), the Mind's visual language
                let groups = Dictionary(grouping: engine.dots, by: \.group)
                for (group, dots) in groups where group >= 0 && dots.count > 1 {
                    var path = Path()
                    path.move(to: at(dots[0]))
                    for d in dots.dropFirst() { path.addLine(to: at(d)) }
                    if dots[0].closes { path.closeSubpath() }
                    g.stroke(path, with: .color(dots[0].color.opacity(0.22)),
                             style: StrokeStyle(lineWidth: 0.7, lineJoin: .round))
                }
                // then the dots, each with a soft halo so they read as points
                // of light on black, not flat pixels
                for d in engine.dots {
                    let p = at(d)
                    let halo = CGRect(x: p.x - d.r * 3.2, y: p.y - d.r * 3.2,
                                      width: d.r * 6.4, height: d.r * 6.4)
                    g.fill(Path(ellipseIn: halo), with: .color(d.color.opacity(d.alpha * 0.14)))
                    let core = CGRect(x: p.x - d.r, y: p.y - d.r,
                                      width: d.r * 2, height: d.r * 2)
                    g.fill(Path(ellipseIn: core), with: .color(d.color.opacity(d.alpha)))
                }
                for c in engine.captions {
                    g.draw(Text(c.text)
                             .font(.system(size: 9, design: .monospaced))
                             .foregroundColor(c.color),
                           at: CGPoint(x: c.x * size.width, y: c.y * size.height))
                }
            }
            VStack(alignment: .leading, spacing: 2) {
                if !engine.reading.isEmpty {
                    Text(engine.reading)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(Color(red: 0.75, green: 0.8, blue: 0.9))
                }
                Text(engine.status)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(Color(red: 0.55, green: 0.6, blue: 0.7).opacity(0.75))
            }
            .padding(.leading, 10)
            .padding(.bottom, 8)
        }
        .onAppear { engine.start() }
        .onDisappear { engine.stop() }
    }
}
