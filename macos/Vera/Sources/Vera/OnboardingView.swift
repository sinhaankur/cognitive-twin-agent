import SwiftUI

/// First run, no terminal: name her, see that her brain is coming up, and
/// learn the three things that matter — talk (⌥Space or her name), teach her
/// a voice, and that every sense is a switch you own. One card, then gone.
struct OnboardingView: View {
    @ObservedObject var model: AppModel
    var done: () -> Void

    @State private var name: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                SiriOrb(amplitude: 0.25, phase: 1.2,
                        tint: Color(red: 0.3, green: 0.45, blue: 0.95))
                    .frame(width: 44, height: 44)
                VStack(alignment: .leading, spacing: 2) {
                    Text("She's yours").font(.title3.weight(.semibold))
                    Text("private, on this Mac, already someone — better once she's someone you name")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }

            TextField("Her name (you can change it anytime)", text: $name)
                .textFieldStyle(.roundedBorder)

            HStack(spacing: 8) {
                Circle().fill(model.serverUp ? .green : .orange).frame(width: 8, height: 8)
                Text(model.serverUp ? "her brain is running (local model)"
                                    : "her brain is starting — needs Ollama (`brew install ollama`)")
                    .font(.caption).foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 6) {
                Label("Talk from anywhere: ⌥Space — or turn on “Wake on her name”",
                      systemImage: "keyboard")
                Label("Give her a real voice: menu → “Teach her a voice…” — or a 5s clip through Voice Harvester",
                      systemImage: "waveform")
                Label("Her senses (camera, hearing, Photos) are switches in the menu — all off until you say",
                      systemImage: "switch.2")
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            HStack {
                Spacer()
                Button("Start") {
                    let n = name.trimmingCharacters(in: .whitespaces)
                    if !n.isEmpty { model.assistantName = n }
                    done()
                }
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(22)
        .frame(width: 430)
        .onAppear { name = model.assistantName }
    }
}
