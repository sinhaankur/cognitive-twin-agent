import SwiftUI

/// Settings sheet: pick the local model, toggle spoken replies, and a few
/// privacy controls. Kept simple and native.
struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Settings").font(.title2.weight(.semibold))
                Spacer()
                Button { dismiss() } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title3).foregroundStyle(.secondary)
                }.buttonStyle(.plain)
            }
            .padding(.bottom, 18)

            Form {
                Section("Model") {
                    Picker("Local model", selection: Binding(
                        get: { model.modelName },
                        set: { model.selectModel($0) }
                    )) {
                        if model.availableModels.isEmpty {
                            Text(model.modelName).tag(model.modelName)
                        }
                        ForEach(model.availableModels, id: \.self) { m in
                            Text(m).tag(m)
                        }
                    }
                    .pickerStyle(.menu)

                    Button {
                        model.refreshModels()
                    } label: {
                        Label("Refresh installed models", systemImage: "arrow.clockwise")
                    }

                    Text("Models run locally via Ollama. Pull more with `ollama pull <name>` in Terminal.")
                        .font(.caption).foregroundStyle(.secondary)

                    HStack(spacing: 6) {
                        Image(systemName: model.appleAvailable ? "apple.logo" : "exclamationmark.triangle")
                            .font(.caption)
                        Text(model.appleStatus)
                            .font(.caption)
                    }
                    .foregroundStyle(model.appleAvailable ? .green : .secondary)
                }

                Section("Voice") {
                    Toggle("Speak replies aloud", isOn: $model.speakReplies)
                }

                Section("Privacy") {
                    LabeledContent("Conversation memory", value: "stored on this Mac only")
                    Button(role: .destructive) {
                        model.clearMemory()
                    } label: {
                        Label("Clear local memory", systemImage: "trash")
                    }
                    Text("Everything stays on-device. Nothing is sent to the cloud.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)

            HStack {
                Circle().fill(model.serverUp ? .green : .orange).frame(width: 7, height: 7)
                Text(model.serverUp ? "local agent connected" : "agent starting…")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text("Twin Voice").font(.caption).foregroundStyle(.tertiary)
            }
            .padding(.top, 14)
        }
        .padding(22)
        .frame(width: 420, height: 480)
        .onAppear { model.refreshModels() }
    }
}
