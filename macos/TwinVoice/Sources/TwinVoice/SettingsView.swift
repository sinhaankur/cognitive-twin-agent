import SwiftUI

/// Settings sheet: pick the local model, toggle spoken replies, and a few
/// privacy controls. Kept simple and native.
struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss

    /// Friendly label for a (possibly provider-tagged) model id. Server tags
    /// OpenAI-backend models as "lmstudio/<name>"; show that as "<name> · LM Studio".
    static func displayName(_ id: String) -> String {
        guard let slash = id.firstIndex(of: "/") else { return id }
        let label = String(id[..<slash])
        let name = String(id[id.index(after: slash)...])
        guard !label.isEmpty, !name.isEmpty else { return id }
        let provider = label == "lmstudio" ? "LM Studio" : label
        return "\(name) · \(provider)"
    }

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
                            Text(Self.displayName(m)).tag(m)
                        }
                    }
                    .pickerStyle(.menu)

                    Button {
                        model.refreshModels()
                    } label: {
                        Label("Refresh available models", systemImage: "arrow.clockwise")
                    }

                    Text("Models run locally via Ollama or an OpenAI-compatible server (LM Studio, llama.cpp, Jan). Pull Ollama models with `ollama pull <name>`; for LM Studio, load a model and start its local server.")
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

                Section("Customize") {
                    HStack {
                        Text("Name your twin")
                        Spacer()
                        TextField("e.g. Anita, Mom, Dad…", text: $model.assistantName)
                            .multilineTextAlignment(.trailing)
                            .frame(maxWidth: 200)
                            .onSubmit { model.renamed() }
                    }
                    Text("Call your twin whatever feels right — it's yours. The name shows up everywhere and shapes how it refers to itself.")
                        .font(.caption).foregroundStyle(.secondary)

                    Button {
                        model.openVoiceLearn?()
                    } label: {
                        Label("Teach \(model.assistantName) a loved one's voice", systemImage: "heart.text.square")
                    }
                    Text("Let \(model.assistantName) learn how someone spoke — from their messages or a voice recording — and carry their warmth forward. Stays on this Mac.")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Section("Learning") {
                    Toggle("Learn how I work (watch my active app)",
                           isOn: Binding(get: { model.activityEnabled },
                                         set: { model.setActivityEnabled($0) }))
                    Toggle("Private mode — pause all observation",
                           isOn: Binding(get: { model.activityPrivate },
                                         set: { model.setPrivate($0) }))
                    Button { model.snooze(30) } label: {
                        Label("Snooze 30 minutes", systemImage: "moon.zzz")
                    }
                    Text("\(model.assistantName) only learns your work patterns (which apps, when) when this is on — and never while Private. All on this Mac; turn it off any time.")
                        .font(.caption).foregroundStyle(.secondary)
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
