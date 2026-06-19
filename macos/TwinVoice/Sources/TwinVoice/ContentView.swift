import SwiftUI
import AppKit

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var phase: CGFloat = 0
    // drives the flowing wave
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 22) {
            Spacer(minLength: 8)

            // --- the Siri orb / wave ---
            SiriOrb(amplitude: model.amplitude, phase: phase, tint: model.tint)
                .frame(width: 240, height: 240)
                .onTapGesture { model.micTapped() }

            // --- transcript (what you said) ---
            Text(model.transcript.isEmpty ? " " : model.transcript)
                .font(.title3.weight(.medium))
                .foregroundStyle(.primary)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .padding(.horizontal, 24)

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

            // --- mic button + status (Siri-style: doubles as Stop) ---
            Button(action: { model.micTapped() }) {
                HStack(spacing: 8) {
                    Image(systemName: buttonIcon)
                    Text(buttonLabel)
                }
                .font(.system(size: 14, weight: .semibold))
                .padding(.horizontal, 22).padding(.vertical, 11)
                .background(Capsule().fill(buttonColor))
                .foregroundStyle(.white)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.space, modifiers: [])   // Space to talk/stop, like a push button

            statusLine
                .padding(.bottom, 14)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onReceive(timer) { _ in
            // advance the wave; speed scales with how "active" we are
            let speed = 0.06 + model.amplitude * 0.22
            phase += speed
            model.syncPhase()
        }
    }

    // Siri-style button: Speak → Listening (stop) → Stop (interrupt speech).
    private var buttonIcon: String {
        if model.voice.isSpeaking { return "stop.circle.fill" }
        if model.voice.isListening { return "stop.fill" }
        return "mic.fill"
    }
    private var buttonLabel: String {
        if model.voice.isSpeaking { return "Stop" }
        if model.voice.isListening { return "Listening…" }
        return "Speak"
    }
    private var buttonColor: Color {
        if model.voice.isSpeaking { return Color.orange.opacity(0.9) }
        if model.voice.isListening { return Color.red.opacity(0.9) }
        return Color.accentColor
    }

    private var statusLine: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(model.serverUp ? Color.green : Color.orange)
                .frame(width: 7, height: 7)
            Text(model.serverUp
                 ? "twin voice · local · \(model.modelName)"
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
