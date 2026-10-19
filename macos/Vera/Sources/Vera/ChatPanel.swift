import SwiftUI

/// The chat view — opens from the floating orb. A calm, premium conversation:
/// her replies read as clean, generous text (not a loud bubble); your messages
/// sit in a soft accent bubble; a warm empty state when there's nothing yet.
/// Text-first, markdown, file attach, and the voice toggle all live here.
struct ChatPanel: View {
    @ObservedObject var model: AppModel
    @State private var typed = ""
    @FocusState private var focused: Bool
    // Orb animation comes from the ONE shared driver (model.orbPhase) — no
    // per-view 60fps timer, so this panel rests when she rests.

    // Vera's accent — warm sandstone gold, now from the shared token system
    // (VeraTokens.accent) so it stays consistent across the app + adapts
    // light/dark. Alias kept so existing references read unchanged.
    private static let gold = VeraTokens.accent

    var body: some View {
        VStack(spacing: 0) {
            header
            // Her "See me" sense lives HERE — inside the panel, sliding in under
            // the header — not an orphan window. One integrated surface.
            if model.eyeOn {
                FaceStrip(model: model)
                    .transition(.asymmetric(
                        insertion: .push(from: .top).combined(with: .opacity),
                        removal: .opacity))
            }
            conversation
            inputBar
        }
        .animation(.easeOut(duration: 0.28), value: model.eyeOn)
        .background(Color.black.opacity(0.001))     // let the window material show
        .onAppear {
            focused = true
            model.voice.refreshPermissionState()   // live status, no stale banner
        }
        // re-check when the app comes back to the front (e.g. after the user
        // flipped the toggle in System Settings) so the banner clears itself.
        .onReceive(NotificationCenter.default.publisher(
            for: NSApplication.didBecomeActiveNotification)) { _ in
            model.voice.refreshPermissionState()
        }
    }

    // MARK: - Header
    // When she's simply present, the sub-line shows whose voice you're hearing;
    // the moment anything is happening (waking / listening / thinking / speaking /
    // warming the voice) it shows that honest state instead.
    private var statusSubline: String {
        if model.status == .ready {
            return model.clonedVoiceReady
                ? "in \(model.assistantName)'s voice"
                : "voice: \(model.activeVoiceLabel)"
        }
        return model.statusLine
    }
    private var statusTint: Color {
        switch model.status {
        case .ready:        return model.clonedVoiceReady ? .pink.opacity(0.9) : .secondary
        case .needsMic:     return .orange
        case .listening:    return .red.opacity(0.85)
        default:            return .secondary
        }
    }

    private var header: some View {
        HStack(spacing: 11) {
            LiveOrb(model: model, size: 32)   // isolated: ticks here, not the panel
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(model.assistantName)
                        .font(.system(size: 14, weight: .semibold))
                    if model.clonedVoiceReady {
                        Image(systemName: "heart.fill")
                            .font(.system(size: 9)).foregroundStyle(.pink)
                            .help("Speaking in \(model.assistantName)'s own cloned voice")
                    }
                }
                HStack(spacing: 5) {
                    Circle()
                        .fill(model.serverUp ? VeraTokens.accent : VeraTokens.warn)
                        .frame(width: 5, height: 5)
                    // The LIVE, honest status — the words that carry the feeling of
                    // what she's doing right now (waking her mind… / listening… /
                    // thinking… / warming her voice… / here with you). Never a
                    // frozen, silent header; if it's loading, it SAYS so. When she's
                    // simply present, show which voice you're hearing instead.
                    Text(statusSubline)
                        .font(.system(size: 10.5, design: .default))
                        .foregroundStyle(statusTint)
                    // a tiny breathing dot while loading/working, so you can SEE it's
                    // alive and not stuck (Claude-style "working…").
                    if model.isBusyState {
                        ProgressView()
                            .controlSize(.mini)
                            .scaleEffect(0.6)
                            .frame(width: 10, height: 10)
                    }
                }
            }
            Spacer()
            headerButtons
        }
        .padding(.horizontal, 16)
        .padding(.top, 14).padding(.bottom, 12)
        .overlay(alignment: .bottom) {
            Rectangle().fill(VeraTokens.line).frame(height: 1)
        }
    }

    private var headerButtons: some View {
        HStack(spacing: 2) {
            iconButton(model.speakReplies ? "speaker.wave.2.fill" : "speaker.slash.fill",
                       on: model.speakReplies,
                       help: model.speakReplies
                        ? "Speaking replies aloud. Click for text-only."
                        : "Text-only. Click to let her speak aloud. (Voice input always gets a spoken reply.)") {
                model.speakReplies.toggle()
            }
            iconButton(model.eyeOn ? "eye.fill" : "eye.slash", on: model.eyeOn,
                       help: model.eyeOn
                        ? "She can see you — face cues only, on-device. Click to stop."
                        : "Let her see you (opt-in): face cues only, on-device.") {
                model.toggleEye?()
            }
            iconButton("ear", on: model.ear.on,
                       help: model.ear.on
                        ? "Hearing the room — sound types only, never recorded. Click to stop."
                        : "Let her hear the room (opt-in): sound types only, never recorded.") {
                model.ear.toggle()
            }
            iconButton(model.voiceMode ? "waveform.circle.fill" : "waveform.circle",
                       on: model.voiceMode,
                       help: model.voiceMode
                        ? "Hands-free voice: she listens again after each reply. Click for tap-to-talk."
                        : "Tap-to-talk. Click for hands-free voice (she keeps listening between turns).") {
                model.voiceMode.toggle()
            }
            iconButton("gearshape", on: false, help: "Settings") {
                model.openSettings?()
            }
        }
    }

    private func iconButton(_ name: String, on: Bool, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: name)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(on ? Self.gold : Color.secondary)
                .frame(width: 30, height: 30)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(on ? Self.gold.opacity(0.14) : Color.clear)
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(help)
    }

    // MARK: - Conversation
    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                if model.turns.isEmpty && model.phase != .thinking {
                    emptyState
                } else {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        ForEach(model.turns) { turn in
                            TurnBubble(turn: turn)
                                .id(turn.id)
                        }
                        if model.phase == .thinking {
                            ThinkingRow(phase: model.orbPhase,
                                        elapsed: Date().timeIntervalSince(model.thinkingSince))
                                .id("thinking")
                                .transition(.opacity)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 18).padding(.bottom, 14)
                }
            }
            .animation(.easeOut(duration: 0.28), value: model.turns.count)
            .onChange(of: model.turns.count) { _ in
                if let last = model.turns.last {
                    withAnimation(.easeOut(duration: 0.3)) { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
            .onChange(of: model.turns.last?.text) { _ in
                if let last = model.turns.last, !last.isUser {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
            .onChange(of: model.phase) { p in
                if p == .thinking { withAnimation { proxy.scrollTo("thinking", anchor: .bottom) } }
            }
        }
    }

    // A warm, calm first impression instead of a blank panel.
    private var emptyState: some View {
        VStack(spacing: 14) {
            LiveOrb(model: model, size: 56)   // isolated animating orb
                .opacity(0.9)
            VStack(spacing: 5) {
                Text("I'm here.")
                    .font(.system(size: 16, weight: .semibold))
                Text("Say anything — how your day went, what you're working on, or nothing in particular.")
                    .font(.system(size: 12.5))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 260)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 56).padding(.bottom, 30)
    }

    // MARK: - Input
    // Name the ACTUAL missing permission (mic vs speech) — the old banner always
    // said "microphone" even when speech recognition was the blocked one, which
    // read as a false alarm when mic was clearly enabled in System Settings.
    private var deniedWhat: String {
        let mic = model.voice.micDenied == true
        let speech = model.voice.speechDenied == true
        if mic && speech { return "Microphone & Speech Recognition" }
        if speech { return "Speech Recognition" }
        return "Microphone"
    }
    // only speech is missing (mic is fine) → open the Speech pane instead of Mic
    private var openSpeechPane: Bool {
        model.voice.speechDenied == true && model.voice.micDenied != true
    }
    private var micPermissionBanner: some View {
        HStack(spacing: 9) {
            Image(systemName: "mic.slash.fill").foregroundStyle(VeraTokens.warn)
            VStack(alignment: .leading, spacing: 1) {
                Text("Allow \(deniedWhat) to talk").font(.system(size: 12, weight: .semibold))
                Text("Typing works meanwhile. If you just turned it on, tap the mic again.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            Button("Open…") {
                model.voice.openPrivacySettings(speech: openSpeechPane)
            }
                .font(.system(size: 11, weight: .semibold))
                .buttonStyle(.borderedProminent).controlSize(.small)
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .background(VeraTokens.warnSoft)
        .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(VeraTokens.warn.opacity(0.4)))
        .clipShape(RoundedRectangle(cornerRadius: 11))
    }

    private var inputBar: some View {
        VStack(spacing: 7) {
            // Show the hint ONLY after a real failed mic tap (permissionNeeded) —
            // never from stale cached TCC status, which read "off" even right after
            // the user flipped the switch ON. It clears the instant the mic works.
            if model.voice.permissionNeeded { micPermissionBanner }
            if model.voice.isListening {
                HStack(spacing: 7) {
                    Image(systemName: "waveform")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(VeraTokens.danger)
                        .opacity(0.55 + Double(model.voice.level) * 0.45)
                    Text(model.voice.transcript.isEmpty ? "listening…" : model.voice.transcript)
                        .font(.system(size: 12))
                        .foregroundStyle(model.voice.transcript.isEmpty ? .secondary : .primary)
                        .lineLimit(1)
                        .truncationMode(.head)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 6)
                .transition(.opacity)
            }
            if let a = model.pendingAttachment {
                HStack(spacing: 7) {
                    Image(systemName: "doc.text.fill").font(.system(size: 11)).foregroundStyle(Self.gold)
                    Text(a.name).font(.system(size: 11.5)).lineLimit(1)
                    Button { model.pendingAttachment = nil } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 12))
                    }.buttonStyle(.plain).foregroundStyle(.secondary)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: 9).fill(Color.primary.opacity(0.06)))
                .transition(.opacity)
            }
            inputRow
        }
        .padding(.horizontal, 14).padding(.top, 10).padding(.bottom, 13)
        .animation(.easeOut(duration: 0.2), value: model.voice.isListening)
        .animation(.easeOut(duration: 0.2), value: model.pendingAttachment != nil)
        .overlay(alignment: .top) {
            Rectangle().fill(VeraTokens.line).frame(height: 1)
        }
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

    private var canSend: Bool {
        !typed.trimmingCharacters(in: .whitespaces).isEmpty || model.pendingAttachment != nil
    }

    private var inputRow: some View {
        HStack(spacing: 10) {
            Button(action: pickFile) {
                Image(systemName: "paperclip")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 26, height: 30)
                    .contentShape(Rectangle())
            }.buttonStyle(.plain)
            .help("Attach a file (PDF, text, code) — read on-device, nothing uploaded")

            TextField(model.voice.isListening ? "type to cancel listening…" : "Message \(model.assistantName)…",
                      text: $typed, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 13.5))
                .lineLimit(1...6)
                .focused($focused)
                .onSubmit(send)
                .onChange(of: typed) { v in
                    if model.voice.isListening && !v.isEmpty {
                        model.voice.stopListening(submit: false)
                    }
                }
                .padding(.vertical, 8)

            Button(action: { model.micTapped() }) {
                Image(systemName: model.voice.isSpeaking ? "stop.fill"
                      : model.voice.isListening ? "waveform" : "mic.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(
                        model.voice.isSpeaking ? VeraTokens.warn
                        : model.voice.isListening ? VeraTokens.danger : Self.gold))
            }.buttonStyle(.plain)
            .help(model.voice.isListening ? "Stop listening" : "Talk to her")

            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 27))
                    .foregroundStyle(canSend ? Self.gold : Color.secondary.opacity(0.5))
                    .animation(.easeOut(duration: 0.15), value: canSend)
            }.buttonStyle(.plain)
            .disabled(!canSend)
        }
        .padding(.leading, 14).padding(.trailing, 6)
        .background(
            Capsule(style: .continuous)
                .fill(.ultraThinMaterial)
                .overlay(Capsule(style: .continuous).strokeBorder(
                    focused ? Self.gold.opacity(0.35) : Color.primary.opacity(0.12), lineWidth: 1))
        )
        .animation(.easeOut(duration: 0.2), value: focused)
    }

    private func send() {
        let t = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty || model.pendingAttachment != nil else { return }
        typed = ""
        model.submitText(t.isEmpty ? "Here's a file — take a look." : t)
    }
}

/// Her processing indicator — a Claude-CLI-style status: a shimmering word
/// ("Thinking…") beside three breathing dots, aligned like one of her replies
/// (same thin gold accent bar). Clear feedback that she heard you and is working,
/// so the chat never feels dead while she composes a reply.
private struct ThinkingRow: View {
    let phase: CGFloat
    var elapsed: TimeInterval = 0
    private var gold: Color { VeraTokens.accent }
    // a gentle rotation of words so it feels alive, not stuck on one label — and
    // on a long wait it REASSURES (warming up / almost there) so the user always
    // knows it's working, never stuck. Micro-detail, but it's the whole feeling.
    private let words = ["Thinking", "Thinking", "Reflecting", "Thinking", "Composing"]
    private var word: String {
        if elapsed > 22 { return "Almost there" }
        if elapsed > 10 { return "Still thinking" }
        if elapsed > 4  { return "Warming up" }
        return words[Int(phase / 18) % words.count]
    }

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            // the same thin gold accent bar her replies use, so this reads as "her"
            RoundedRectangle(cornerRadius: 2)
                .fill(gold.opacity(0.55))
                .frame(width: 2.5, height: 16)
                .padding(.top, 1)
            HStack(spacing: 7) {
                Text(word)
                    .font(.system(size: 13, weight: .medium))
                    // a soft shimmer sweeping the word (like a 'processing' glow)
                    .foregroundStyle(gold.opacity(0.55 + 0.35 * (0.5 + 0.5 * sin(Double(phase) * 0.12))))
                HStack(spacing: 4) {
                    ForEach(0..<3, id: \.self) { i in
                        Circle()
                            .fill(gold)
                            .frame(width: 4.5, height: 4.5)
                            .opacity(0.25 + 0.6 * (0.5 + 0.5 * sin(Double(phase) * 0.9 - Double(i) * 0.9)))
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .transition(.opacity)
    }
}

/// One turn. Her replies read as clean, generous text with a subtle gold accent
/// bar — not a loud bubble (that's what made it feel dated). Your messages sit in
/// a soft accent bubble, right-aligned. Markdown-rendered, selectable.
private struct TurnBubble: View {
    let turn: ChatTurn
    private var gold: Color { VeraTokens.accent }

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
        if turn.isUser {
            // your message — a soft accent bubble, right-aligned, max 78% width
            HStack {
                Spacer(minLength: 40)
                Text(turn.text)
                    .font(.system(size: 13.5))
                    .lineSpacing(2.5)
                    .textSelection(.enabled)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .background(
                        RoundedRectangle(cornerRadius: 17, style: .continuous)
                            .fill(gold.opacity(0.9))
                    )
            }
            .transition(.asymmetric(
                insertion: .move(edge: .trailing).combined(with: .opacity),
                removal: .opacity))
        } else {
            // her reply — generous clean text with a thin gold accent on the left
            HStack(alignment: .top, spacing: 11) {
                RoundedRectangle(cornerRadius: 2)
                    .fill(gold.opacity(0.55))
                    .frame(width: 2.5)
                    .padding(.vertical, 2)
                Text(rendered)
                    .font(.system(size: 14))
                    .lineSpacing(3.5)
                    .textSelection(.enabled)
                    // Adaptive: .primary reads dark on light, light on dark — so her
                    // reply is legible in BOTH appearances (was hardcoded cream,
                    // invisible on a light background).
                    .foregroundStyle(.primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .transition(.asymmetric(
                insertion: .move(edge: .leading).combined(with: .opacity),
                removal: .opacity))
        }
    }
}
