import SwiftUI
import AVFoundation

/// FaceStrip — her "See me" sense, folded into the chat panel. Built like a real
/// app: the real camera feed, AUTO-FRAMED on your face (it zooms + glides to keep
/// you centred, Face-ID style), with a clean amber particle overlay that reads
/// your expression and colours itself to the emotion.
///
///   • Auto-focus: the video is zoomed/offset by the engine's smoothed face frame
///     (frameCenter / frameSpan) — the SAME frame the landmark dots live in — so
///     the overlay sits exactly on your face and you fill the view, not the room.
///   • Emotion-aware: the overlay + reading shift with what she reads — warm gold
///     when you smile, calm amber when attentive, a cooler tone when tense.
///   • Motion: soft particles settle on your features with a travelling light.
///
/// Opt-in contract unchanged: camera runs only while this is on screen; Stop forgets.
struct FaceStrip: View {
    @ObservedObject var model: AppModel
    @StateObject private var engine = FaceEngine.shared
    @State private var naming = false          // the "who is this?" enroll popover
    @State private var enrollName = ""
    @State private var enrollNote = ""

    // ── emotion → colour + word ────────────────────────────────────────────────
    private enum Mood { case happy, attentive, tense, neutral }
    private var mood: Mood {
        if engine.readSmile > 0.45 { return .happy }
        if engine.readFrown > 0.4 || engine.readBrow > 0.5 { return .tense }
        if engine.readAttending { return .attentive }
        return .neutral
    }
    private var moodColor: Color {
        switch mood {
        case .happy:     return Color(red: 0.95, green: 0.74, blue: 0.36)  // warm gold
        case .attentive: return VeraTokens.accent                          // her amber
        case .tense:     return Color(red: 0.80, green: 0.60, blue: 0.47)  // cooler clay
        case .neutral:   return VeraTokens.accent.opacity(0.85)
        }
    }
    private var moodWord: String {
        switch mood {
        case .happy: return "warm"; case .attentive: return "attentive"
        case .tense: return "focused"; case .neutral: return "here"
        }
    }

    private var readingLine: String {
        guard engine.facePresent else { return "looking for you — step into frame" }
        if !engine.reading.isEmpty { return engine.reading }
        return "she sees you"
    }

    // Auto-frame transform for the video — a GENTLE zoom that keeps your whole
    // head in view (never a tight, over-cropped close-up). Capped at 1.35× and the
    // frameSpan floored high so it eases toward you without cutting off the top of
    // your head. Pulled back from the old 2.4× that read as "over-focused".
    private var zoom: CGFloat { max(1.0, min(1.35, 1.0 / max(0.74, engine.frameSpan))) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack {
                Color(red: 0.04, green: 0.035, blue: 0.03)

                // 1) the real camera feed — AUTO-FRAMED on the face (zoom + glide).
                GeometryReader { geo in
                    CameraPreview(session: engine.captureSession)
                        .scaleEffect(zoom)
                        .offset(x: (0.5 - engine.frameCenter.x) * geo.size.width * zoom,
                                y: (0.5 - engine.frameCenter.y) * geo.size.height * zoom)
                        .animation(.easeOut(duration: 0.25), value: engine.frameCenter)
                        .animation(.easeOut(duration: 0.25), value: engine.frameSpan)
                }
                .clipped()
                .overlay(
                    RadialGradient(colors: [.clear, .black.opacity(0.3)],
                                   center: .center, startRadius: 50, endRadius: 230)
                        .allowsHitTesting(false))

                // 2) quiet instrument corner-ticks only — NO landmark overlay on the
                //    face (the amber tracing read as noise over the real video).
                //    When no face is in frame yet, a calm breathing reticle at centre.
                TimelineView(.periodic(from: .now, by: 1.0 / 20.0)) { tl in
                    let t = tl.date.timeIntervalSinceReferenceDate
                    Canvas { g, size in
                        drawFrameTicks(g: &g, size: size)
                        if engine.dots.isEmpty { drawReticle(g: &g, size: size, t: t) }
                    }
                    .allowsHitTesting(false)
                }

                // 3) enhanced reading — a labelled card at the bottom over a scrim.
                VStack(spacing: 0) {
                    Spacer()
                    readingCard
                }
            }
            .frame(height: 176)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(moodColor.opacity(0.22), lineWidth: 1))
            .shadow(color: .black.opacity(0.28), radius: 12, y: 4)

            footer
        }
        .padding(.horizontal, 14).padding(.top, 10)
        .onAppear { engine.start() }
        .onDisappear { engine.stop() }
    }

    // SF Symbol for the current emotion — makes the read instant, not just a word.
    private var moodIcon: String {
        switch mood {
        case .happy: return "face.smiling"
        case .attentive: return "eye"
        case .tense: return "exclamationmark.triangle"
        case .neutral: return "face.dashed"
        }
    }
    // The room read: who's present (NAMED if recognized) + how many looking her way.
    private var roomLine: String {
        if engine.peopleCount <= 0 { return engine.facePresent ? "someone's here" : "no one in view" }
        // the nearest face's name, if FaceID recognized them (on-device).
        let who = engine.recognizedName.map { shortName($0) }
        if engine.peopleCount == 1 { return who ?? "just you" }
        let looking = engine.attendingCount
        let lead = who.map { "\($0) + \(engine.peopleCount - 1) more" }
                     ?? "\(engine.peopleCount) people"
        return "\(lead) · \(looking) looking her way"
    }
    // "Dad — Dr Randhir Kumar Sinha" → "Dad" for the compact room line.
    private func shortName(_ full: String) -> String {
        full.components(separatedBy: " — ").first ?? full
    }

    // ── enhanced reading card: EMOTION (clear) + the ROOM read ─────────────────
    private var readingCard: some View {
        VStack(alignment: .leading, spacing: 5) {
            // row 1 — the emotion, stated clearly as a chip + the trend phrase.
            HStack(spacing: 8) {
                HStack(spacing: 5) {
                    Image(systemName: engine.facePresent ? moodIcon : "viewfinder")
                        .font(.system(size: 10, weight: .semibold))
                    Text(engine.facePresent ? moodWord.capitalized : "Looking")
                        .font(.system(size: 11, weight: .bold))
                }
                .foregroundStyle(.white)
                .padding(.horizontal, 8).padding(.vertical, 3)
                .background(Capsule().fill(moodColor.opacity(0.9)))

                if engine.facePresent, !engine.moodLine.isEmpty {
                    Text(engine.moodLine)
                        .font(.system(size: 10)).foregroundStyle(.white.opacity(0.7))
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
                if engine.facePresent {
                    Text("\(Int(engine.readBlink)) bpm")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.white.opacity(0.4))
                }
            }
            // row 2 — the room read, with a people icon.
            HStack(spacing: 6) {
                Image(systemName: engine.peopleCount > 1 ? "person.2.fill" : "person.fill")
                    .font(.system(size: 9)).foregroundStyle(.white.opacity(0.6))
                Text(roomLine)
                    .font(.system(size: 10.5))
                    .foregroundStyle(.white.opacity(0.78))
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 24).padding(.bottom, 10)
        .background(
            LinearGradient(colors: [.clear, .black.opacity(0.68)],
                           startPoint: .top, endPoint: .bottom)
                .allowsHitTesting(false))
    }

    private var footer: some View {
        HStack(spacing: 6) {
            Image(systemName: "lock.fill").font(.system(size: 8))
            Text("on-device · face cues only · never recorded")
                .font(.system(size: 9.5))
            Spacer(minLength: 0)
            // When a face is in frame but NOT recognized, offer to name them —
            // enrollment is the base of the legacy/virtual-you arc, and it's how
            // the room read becomes "you + Dad".
            if engine.facePresent, engine.recognizedName == nil {
                Button { naming = true } label: {
                    Label("Who is this?", systemImage: "person.badge.plus")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(VeraTokens.accent)
                }
                .buttonStyle(.plain)
                .popover(isPresented: $naming, arrowEdge: .bottom) { enrollPopover }
            }
            Button { model.toggleEye?() } label: {
                Text("Stop").font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(VeraTokens.accent)
            }.buttonStyle(.plain)
        }
        .foregroundStyle(.secondary)
        .padding(.top, 7).padding(.horizontal, 3)
    }

    private var enrollPopover: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Name this person").font(.system(size: 13, weight: .semibold))
            Text("She'll recognize them next time — enrolled on this Mac, never uploaded. (e.g. “Dad — Dr Randhir Kumar Sinha”.)")
                .font(.system(size: 11)).foregroundStyle(.secondary).frame(width: 240)
            TextField("Name or relationship", text: $enrollName)
                .textFieldStyle(.roundedBorder)
                .onSubmit(saveEnrollment)
            if !enrollNote.isEmpty {
                Text(enrollNote).font(.system(size: 10.5)).foregroundStyle(VeraTokens.accent)
            }
            HStack {
                Spacer()
                Button("Save") { saveEnrollment() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(enrollName.trimmingCharacters(in: .whitespaces).count < 2
                              || !engine.hasFaceToEnroll)
            }
        }
        .padding(14)
    }

    private func saveEnrollment() {
        let n = enrollName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard n.count >= 2 else { return }
        let count = engine.enrollCurrentFace(as: n)
        if count > 0 {
            enrollNote = "Saved \(shortName(n)) · \(count) view\(count == 1 ? "" : "s")"
            enrollName = ""
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.1) { naming = false; enrollNote = "" }
        } else {
            enrollNote = "Hold still a moment — no clear face yet."
        }
    }

    private func drawReticle(g: inout GraphicsContext, size: CGSize, t: TimeInterval) {
        let c = CGPoint(x: size.width / 2, y: size.height / 2)
        let breathe = 0.5 + 0.5 * sin(t * 1.6)
        let r = min(size.width, size.height) * (0.16 + 0.015 * breathe)
        let ring = Path(ellipseIn: CGRect(x: c.x - r, y: c.y - r, width: r * 2, height: r * 2))
        g.stroke(ring, with: .color(VeraTokens.accent.opacity(0.35 + 0.25 * breathe)),
                 style: StrokeStyle(lineWidth: 1.4, dash: [3, 7], dashPhase: CGFloat(t * 6)))
    }

    private func drawFrameTicks(g: inout GraphicsContext, size: CGSize) {
        let m: CGFloat = 9, l: CGFloat = 12
        var p = Path()
        for (x, y, sx, sy): (CGFloat, CGFloat, CGFloat, CGFloat) in
            [(m, m, 1, 1), (size.width - m, m, -1, 1),
             (m, size.height - m, 1, -1), (size.width - m, size.height - m, -1, -1)] {
            p.move(to: CGPoint(x: x + sx * l, y: y))
            p.addLine(to: CGPoint(x: x, y: y))
            p.addLine(to: CGPoint(x: x, y: y + sy * l))
        }
        g.stroke(p, with: .color(.white.opacity(0.22)), lineWidth: 1)
    }
}

/// A live camera preview backed by the SAME AVCaptureSession FaceEngine runs —
/// no second camera. Mirrored (selfie), aspect-fill; FaceStrip zooms/offsets it to
/// auto-frame the face.
private struct CameraPreview: NSViewRepresentable {
    let session: AVCaptureSession

    func makeNSView(context: Context) -> PreviewView {
        let v = PreviewView()
        v.wantsLayer = true
        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.backgroundColor = NSColor(calibratedRed: 0.04, green: 0.035, blue: 0.03, alpha: 1).cgColor
        layer.videoGravity = .resizeAspectFill
        if let conn = layer.connection, conn.isVideoMirroringSupported {
            conn.automaticallyAdjustsVideoMirroring = false
            conn.isVideoMirrored = true
        }
        v.previewLayer = layer
        v.layer = layer
        return v
    }

    func updateNSView(_ nsView: PreviewView, context: Context) {}

    final class PreviewView: NSView {
        var previewLayer: AVCaptureVideoPreviewLayer?
        override func layout() { super.layout(); previewLayer?.frame = bounds }
    }
}
