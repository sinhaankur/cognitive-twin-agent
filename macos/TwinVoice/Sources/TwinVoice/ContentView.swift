import SwiftUI
import AppKit

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var phase: CGFloat = 0
    @State private var typed: String = ""
    @FocusState private var inputFocused: Bool
    // drives the orb animation
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 18) {
            // --- top bar: settings gear ---
            HStack {
                Spacer()
                Button { model.refreshModels(); model.showSettings = true } label: {
                    Image(systemName: "gearshape")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Settings")
            }
            .padding(.top, 10)
            .padding(.horizontal, 16)

            // --- the Siri orb ---
            SiriOrb(amplitude: model.amplitude, phase: phase, tint: model.tint)
                .frame(width: 220, height: 220)
                .onTapGesture { model.micTapped() }

            // --- transcript (what you said) ---
            Text(model.transcript.isEmpty ? " " : model.transcript)
                .font(.title3.weight(.medium))
                .foregroundStyle(.primary)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .padding(.horizontal, 24)
                .animation(.easeInOut(duration: 0.2), value: model.transcript)

            // --- answer (what the twin said) ---
            ScrollView {
                Text(model.answer)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 26)
                    .frame(maxWidth: .infinity)
            }
            .frame(maxHeight: 120)

            Spacer(minLength: 4)

            // --- unified input bar: text field + mic, one clean control ---
            inputBar
                .padding(.horizontal, 20)

            statusLine
                .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onReceive(timer) { _ in
            // advance the orb swirl; speed scales with how "active" we are
            let speed = 0.05 + model.amplitude * 0.30
            phase += speed
            model.syncPhase()
        }
        .sheet(isPresented: $model.showSettings) {
            SettingsView().environmentObject(model)
        }
    }

    // A single bar: type and press return, or tap the mic to talk. The mic turns
    // red while listening / orange (stop) while speaking.
    private var inputBar: some View {
        HStack(spacing: 10) {
            TextField(inputPlaceholder, text: $typed)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .focused($inputFocused)
                .onSubmit(submitTyped)
                .padding(.vertical, 11)
                .padding(.leading, 16)
                .padding(.trailing, 6)

            Button(action: { model.micTapped() }) {
                Image(systemName: micIcon)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 34, height: 34)
                    .background(Circle().fill(micColor))
                    .overlay(
                        // pulsing ring while listening — subtle "live" cue
                        Circle()
                            .stroke(micColor.opacity(0.5), lineWidth: 2)
                            .scaleEffect(model.voice.isListening ? 1.0 + model.amplitude * 0.6 : 1.0)
                            .opacity(model.voice.isListening ? 0.8 : 0)
                    )
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.space, modifiers: [])
            .padding(.trailing, 6)
        }
        .background(
            Capsule()
                .fill(.ultraThinMaterial)
                .overlay(Capsule().strokeBorder(.white.opacity(0.12), lineWidth: 1))
        )
        .animation(.easeInOut(duration: 0.2), value: model.voice.isListening)
        .animation(.easeInOut(duration: 0.2), value: model.voice.isSpeaking)
    }

    private func submitTyped() {
        let t = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        typed = ""
        model.submitText(t)
    }

    private var inputPlaceholder: String {
        if model.voice.isListening { return "Listening…" }
        if model.voice.isSpeaking { return "Speaking… (tap mic to stop)" }
        return "Ask anything, or tap the mic…"
    }
    private var micIcon: String {
        if model.voice.isSpeaking { return "stop.fill" }
        if model.voice.isListening { return "waveform" }
        return "mic.fill"
    }
    private var micColor: Color {
        if model.voice.isSpeaking { return .orange }
        if model.voice.isListening { return .red }
        return .accentColor
    }

    private var statusLine: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(model.serverUp ? Color.green : Color.orange)
                .frame(width: 7, height: 7)
            Text(model.serverUp
                 ? "twin voice · local · \(SettingsView.displayName(model.modelName))"
                 : "starting local agent…")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(.secondary)
        }
    }
}

/// Native macOS translucent "glass" window background (the real Siri-panel feel).
struct VisualEffectBackground: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let v = NSVisualEffectView()
        v.material = .hudWindow
        v.blendingMode = .behindWindow
        v.state = .active
        return v
    }
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}
