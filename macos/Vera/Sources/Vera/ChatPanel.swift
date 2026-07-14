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
            SiriOrb(amplitude: model.amplitude, phase: phase, tint: model.tint)
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
            Button { model.toggleEye?() } label: {
                Image(systemName: model.eyeOn ? "eye.fill" : "eye.slash")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(model.eyeOn ? Color.cyan : Color.secondary)
            }
            .buttonStyle(.plain)
            .help(model.eyeOn
                  ? "She can see you — motion cues only, on-device. Click to stop."
                  : "Let her see you (opt-in): motion cues only, on-device, nothing stored.")
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
                        Text("thinking…")
                            .font(.caption).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 12)
                    }
                }
                .padding(.vertical, 12)
            }
            .onChange(of: model.turns.count) { _ in
                if let last = model.turns.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            // While listening, the field becomes the live transcript — your
            // words appear as you say them (the Siri detail), then submit
            // themselves when you pause.
            if model.voice.isListening {
                HStack(spacing: 6) {
                    Image(systemName: "waveform")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Color.red)
                        .opacity(0.55 + Double(model.voice.level) * 0.45)
                    Text(model.voice.transcript.isEmpty ? "listening…" : model.voice.transcript)
                        .font(.system(size: 13))
                        .foregroundStyle(model.voice.transcript.isEmpty ? .secondary : .primary)
                        .lineLimit(1)
                        .truncationMode(.head)      // keep the newest words visible
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 9).padding(.leading, 14)
            } else {
                TextField("Ask your twin…", text: $typed)
                    .textFieldStyle(.plain)
                    .focused($focused)
                    .onSubmit(send)
                    .padding(.vertical, 9).padding(.leading, 14)
            }

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
            .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .background(Capsule().fill(.ultraThinMaterial)
            .overlay(Capsule().strokeBorder(.white.opacity(0.12))))
        .padding(12)
    }

    private func send() {
        let t = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        typed = ""
        model.submitText(t)
    }
}

private struct TurnBubble: View {
    let turn: ChatTurn
    var body: some View {
        VStack(alignment: turn.isUser ? .trailing : .leading, spacing: 2) {
            Text(turn.text)
                .font(.system(size: 13))
                .foregroundStyle(turn.isUser ? Color.white : Color.primary)
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 14)
                        .fill(turn.isUser ? Color.accentColor : Color.gray.opacity(0.22)))
        }
        .frame(maxWidth: .infinity, alignment: turn.isUser ? .trailing : .leading)
        .padding(.horizontal, 12)
    }
}
