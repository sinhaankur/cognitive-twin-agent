import SwiftUI

/// The chat view — appears when you click the floating orb (like Siri today).
/// A scrolling conversation + an input bar with a mic. This is item #2 of the
/// two-thing app.
struct ChatPanel: View {
    @ObservedObject var model: AppModel
    @State private var typed = ""
    @State private var phase: CGFloat = 0
    @FocusState private var focused: Bool
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            conversation
            inputBar
        }
        .onReceive(timer) { _ in
            phase += 0.05 + model.amplitude * 0.30
            model.syncPhase()
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            SiriOrb(amplitude: model.amplitude, phase: phase, tint: model.tint, brightness: model.brightness)
                .frame(width: 30, height: 30)
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 5) {
                    Text(model.assistantName).font(.system(size: 13, weight: .semibold))
                    if model.clonedVoiceReady {
                        Image(systemName: "heart.fill")
                            .font(.system(size: 9)).foregroundStyle(.pink)
                            .help("Speaking in her voice")
                    }
                }
                Text(model.serverUp
                     ? (model.clonedVoiceReady ? "her voice" : SettingsView.displayName(model.modelName))
                     : "waking…")
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            // Text-first: she replies in text unless you turn the speaker on.
            Button { model.speakReplies.toggle() } label: {
                Image(systemName: model.speakReplies ? "speaker.wave.2.fill" : "speaker.slash.fill")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(model.speakReplies ? Color.cyan : Color.secondary)
            }
            .buttonStyle(.plain)
            .help(model.speakReplies
                  ? "She speaks her replies aloud. Click for text-only."
                  : "Text-only replies. Click to let her speak aloud. (Talking to her by voice always gets a spoken reply.)")
            Button { model.toggleEye?() } label: {
                Image(systemName: model.eyeOn ? "eye.fill" : "eye.slash")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(model.eyeOn ? Color.cyan : Color.secondary)
            }
            .buttonStyle(.plain)
            .help(model.eyeOn
                  ? "She can see you — face cues only (a smile, a nod), on-device. Click to stop."
                  : "Let her see you (opt-in): face cues only, on-device, nothing stored.")
            Button { model.ear.toggle() } label: {
                Image(systemName: "ear")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(model.ear.on ? Color.cyan : Color.secondary)
            }
            .buttonStyle(.plain)
            .help(model.ear.on
                  ? "She hears the room — sound types only (music, typing), never recorded. Click to stop."
                  : "Let her hear the room (opt-in): sound types only, on-device, never recorded.")
            Button { model.openSettings?() } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help("Settings")
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
    }

    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(model.turns) { turn in
                        TurnBubble(turn: turn)
                            .id(turn.id)
                    }
                    if model.phase == .thinking {
                        // Three dots that breathe in sequence — riding the same
                        // 60 fps phase the mark uses, so "alive" reads consistently.
                        ThinkingDots(phase: phase)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 12)
                            .transition(.opacity)
                    }
                }
                .padding(.vertical, 12)
            }
            .onChange(of: model.turns.count) { _ in
                if let last = model.turns.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            // streaming grows the LAST bubble without changing the count —
            // keep the newest words on screen as they arrive
            .onChange(of: model.turns.last?.text) { _ in
                if let last = model.turns.last, !last.isUser {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }

    // When mic/speech is DENIED, the mic button would silently do nothing
    // ("mic isn't working" / "hi Anita doesn't listen"). Show a clear, one-click
    // fix instead of leaving the user guessing.
    private var micPermissionBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "mic.slash.fill").foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 1) {
                Text("Microphone access is off").font(.system(size: 12, weight: .semibold))
                Text("She can't hear you until you allow it. (Typing still works.)")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Button("Allow…") { model.voice.openPrivacySettings() }
                .font(.system(size: 11, weight: .semibold))
                .buttonStyle(.borderedProminent).controlSize(.small)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(Color.orange.opacity(0.12))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.orange.opacity(0.3)))
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal, 12)
    }

    private var inputBar: some View {
        VStack(spacing: 5) {
            if model.voice.permissionDenied { micPermissionBanner }
            // While listening, your words appear live ABOVE the field (the
            // Siri detail) — the field itself never goes away: no state may
            // ever take typing from the user.
            if model.voice.isListening {
                HStack(spacing: 6) {
                    Image(systemName: "waveform")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Color.red)
                        .opacity(0.55 + Double(model.voice.level) * 0.45)
                    Text(model.voice.transcript.isEmpty ? "listening…" : model.voice.transcript)
                        .font(.system(size: 12))
                        .foregroundStyle(model.voice.transcript.isEmpty ? .secondary : .primary)
                        .lineLimit(1)
                        .truncationMode(.head)      // keep the newest words visible
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 16)
            }
            // a file you've attached shows as a removable chip above the field
            if let a = model.pendingAttachment {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text").font(.system(size: 11))
                    Text(a.name).font(.system(size: 11)).lineLimit(1)
                    Button { model.pendingAttachment = nil } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 11))
                    }.buttonStyle(.plain).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                }
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
            }
            inputRow
        }
        .padding(12)
    }

    private func pickFile() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.pdf, .plainText, .text, .sourceCode,
                                     .json, .rtf, .commaSeparatedText, .data]
        if panel.runModal() == .OK, let url = panel.url {
            model.attachFile(url)
        }
    }

    private var inputRow: some View {
        HStack(spacing: 8) {
            // attach a file (on-device: its text is read locally, never uploaded)
            Button(action: pickFile) {
                Image(systemName: "paperclip")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 28, height: 30)
            }.buttonStyle(.plain)
            .help("Attach a file (PDF, text, code) — read on-device, nothing uploaded")

            TextField(model.voice.isListening ? "type to cancel listening…" : "Ask your twin…",
                      text: $typed)
                .textFieldStyle(.plain)
                .focused($focused)
                .onSubmit(send)
                .onChange(of: typed) { v in
                    // typing is an interruption too — keyboard wins over mic
                    if model.voice.isListening && !v.isEmpty {
                        model.voice.stopListening(submit: false)
                    }
                }
                .padding(.vertical, 9).padding(.leading, 14)

            Button(action: { model.micTapped() }) {
                Image(systemName: model.voice.isSpeaking ? "stop.fill"
                      : model.voice.isListening ? "waveform" : "mic.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(
                        model.voice.isSpeaking ? Color.orange
                        : model.voice.isListening ? Color.red : Color.accentColor))
            }.buttonStyle(.plain)

            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 26)).foregroundStyle(Color.accentColor)
            }.buttonStyle(.plain).padding(.trailing, 8)
            .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty && model.pendingAttachment == nil)
        }
        .background(Capsule().fill(.ultraThinMaterial)
            .overlay(Capsule().strokeBorder(.white.opacity(0.12))))
    }

    private func send() {
        let t = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        // allow sending a bare attachment (with a sensible default ask)
        guard !t.isEmpty || model.pendingAttachment != nil else { return }
        typed = ""
        model.submitText(t.isEmpty ? "Here's a file — take a look." : t)
    }
}

/// Three amber dots that pulse in sequence while Vera thinks — a small, alive
/// touch that matches the hexagon mark's amber and its breathing cadence.
private struct ThinkingDots: View {
    let phase: CGFloat
    private var amber: Color { Color(red: 0.81, green: 0.60, blue: 0.17) }
    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(amber)
                    .frame(width: 5, height: 5)
                    .opacity(0.35 + 0.5 * (0.5 + 0.5 * sin(Double(phase) * 0.9 - Double(i) * 0.9)))
            }
        }
        .padding(.horizontal, 13).padding(.vertical, 9)
        .background(amber.opacity(0.08))
        .clipShape(Capsule())
    }
}

private struct TurnBubble: View {
    let turn: ChatTurn
    private var amber: Color { Color(red: 0.95, green: 0.74, blue: 0.36) }

    // Render her replies as MARKDOWN (bold, lists, `code`, links) so answers read
    // like a real chat — Claude-grade legibility. User text stays verbatim.
    private var rendered: AttributedString {
        if turn.isUser { return AttributedString(turn.text) }
        if let a = try? AttributedString(
            markdown: turn.text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return a
        }
        return AttributedString(turn.text)
    }

    var body: some View {
        Text(rendered)
            .font(.system(size: 13))
            .lineSpacing(2)                          // her words breathe — easier to read
            .textSelection(.enabled)                 // let the user copy replies
            // legible on the dark window: user text is white on accent; her text
            // is a warm off-white on a real amber glass, not near-invisible grey
            .foregroundStyle(turn.isUser ? Color.white
                             : Color(red: 0.97, green: 0.95, blue: 0.90))
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(bubbleFill)
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(turn.isUser ? .clear : amber.opacity(0.35), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(color: turn.isUser ? Color.accentColor.opacity(0.28)
                          : amber.opacity(0.18), radius: 5, y: 2)
            .frame(maxWidth: 300, alignment: turn.isUser ? .trailing : .leading)
            .frame(maxWidth: .infinity, alignment: turn.isUser ? .trailing : .leading)
            .padding(.horizontal, 12)
            .transition(.asymmetric(
                insertion: .move(edge: turn.isUser ? .trailing : .leading)
                    .combined(with: .opacity),
                removal: .opacity))
    }

    // The user speaks in the accent; Vera speaks in a warm amber glass — her
    // replies read as "hers" (matching the hexagon mark), warm and legible, a
    // soft top-to-bottom gradient so the bubble has depth instead of a flat wash.
    private var bubbleFill: some ShapeStyle {
        turn.isUser
            ? AnyShapeStyle(Color.accentColor)
            : AnyShapeStyle(LinearGradient(
                colors: [amber.opacity(0.26), amber.opacity(0.15)],
                startPoint: .top, endPoint: .bottom))
    }
}
