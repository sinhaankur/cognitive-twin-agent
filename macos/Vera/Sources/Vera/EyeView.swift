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
                for d in engine.dots {
                    let x = d.x * size.width, y = d.y * size.height
                    let rect = CGRect(x: x - d.r, y: y - d.r, width: d.r * 2, height: d.r * 2)
                    g.fill(Path(ellipseIn: rect), with: .color(d.color.opacity(d.alpha)))
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
