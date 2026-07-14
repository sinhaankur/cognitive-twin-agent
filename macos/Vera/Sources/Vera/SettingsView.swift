import SwiftUI

/// Settings sheet: pick the local model, toggle spoken replies, and a few
/// privacy controls. Kept simple and native.
struct SettingsView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss

    // export-for-another-device sheet (the memory vault)
    @State private var exporting = false
    @State private var exportPass = ""
    @State private var exportPass2 = ""
    @State private var exportNote = ""

    /// Friendly label for a (possibly provider-tagged) model id.
    static func displayName(_ id: String) -> String {
        if id == AppModel.appleModelID { return id }
        guard let slash = id.firstIndex(of: "/") else { return id }
        let label = String(id[..<slash])
        let name = String(id[id.index(after: slash)...])
        guard !label.isEmpty, !name.isEmpty else { return id }
        return "\(name) · \(providerName(label))"
    }

    /// Which provider a model id belongs to (for grouping).
    static func providerName(_ label: String) -> String {
        switch label.lowercased() {
        case "lmstudio": return "LM Studio"
        case "unhosted": return "Unhosted"
        default: return label.capitalized
        }
    }

    static func provider(of id: String) -> String {
        if id == AppModel.appleModelID { return "Apple Intelligence" }
        if let slash = id.firstIndex(of: "/") {
            return providerName(String(id[..<slash]))
        }
        return "Ollama"
    }

    /// Bare model name for display in a row (provider shown in the group header).
    static func bareName(_ id: String) -> String {
        if id == AppModel.appleModelID { return "On-device (Apple Intelligence)" }
        if let slash = id.firstIndex(of: "/") { return String(id[id.index(after: slash)...]) }
        return id
    }
    func bareName(_ id: String) -> String { Self.bareName(id) }

    /// Providers present in the available models, in a stable, friendly order.
    var groupedProviders: [String] {
        let order = ["Apple Intelligence", "Unhosted", "Ollama", "LM Studio"]
        let present = Set(model.availableModels.map { Self.provider(of: $0) })
        var out = order.filter { present.contains($0) }
        for p in present where !out.contains(p) { out.append(p) }  // any others
        return out
    }
    func modelsFor(_ provider: String) -> [String] {
        model.availableModels.filter { Self.provider(of: $0) == provider }
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
                Section {
                    // LM Studio-style picker: models grouped by provider, each a
                    // tappable row with a checkmark for the active one.
                    if model.availableModels.isEmpty {
                        Text("No models found. Start Ollama / LM Studio / Unhosted, then Refresh.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(groupedProviders, id: \.self) { prov in
                        HStack {
                            Text(prov.uppercased())
                                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                                .foregroundStyle(.secondary)
                            Spacer()
                            if prov == "Unhosted" {
                                Text("your hardware").font(.caption2).foregroundStyle(.green)
                            }
                        }
                        .padding(.top, 4)
                        ForEach(modelsFor(prov), id: \.self) { m in
                            Button { model.selectModel(m) } label: {
                                HStack {
                                    Image(systemName: m == model.modelName ? "checkmark.circle.fill" : "circle")
                                        .foregroundStyle(m == model.modelName ? Color.accentColor : .secondary)
                                    Text(bareName(m))
                                    Spacer()
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    Button { model.refreshModels() } label: {
                        Label("Refresh models", systemImage: "arrow.clockwise")
                    }
                    .padding(.top, 4)
                } header: {
                    Text("Model")
                } footer: {
                    Text("Local via Ollama, LM Studio, or your own Unhosted cluster — or Apple Intelligence on-device. Anita auto-detects Unhosted if it's running.")
                        .font(.caption)
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
                    LabeledContent("Conversation memory", value: "encrypted on this Mac")
                    Button {
                        exporting = true
                    } label: {
                        Label("Export for another device…", systemImage: "square.and.arrow.up")
                    }
                    Button(role: .destructive) {
                        model.clearMemory()
                    } label: {
                        Label("Clear local memory", systemImage: "trash")
                    }
                    Text("Sealed with a key held by this Mac and your account (Keychain) — files copied off this machine read as noise. Export writes one passphrase-encrypted bundle you can import on another device. Nothing is sent to the cloud.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)

            HStack {
                Circle().fill(model.serverUp ? .green : .orange).frame(width: 7, height: 7)
                Text(model.serverUp ? "local agent connected" : "agent starting…")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text("Vera").font(.caption).foregroundStyle(.tertiary)
            }
            .padding(.top, 14)
        }
        .padding(22)
        .frame(width: 420, height: 480)
        .onAppear { model.refreshModels() }
        .sheet(isPresented: $exporting) {
            VStack(alignment: .leading, spacing: 10) {
                Text("Export her memory").font(.headline)
                Text("One encrypted file, locked by a passphrase you choose. On the new device: ctwin vault import <file> — it re-seals for that device.")
                    .font(.caption).foregroundStyle(.secondary)
                SecureField("Passphrase (6+ characters)", text: $exportPass)
                SecureField("Repeat passphrase", text: $exportPass2)
                if !exportNote.isEmpty {
                    Text(exportNote).font(.caption).foregroundStyle(.secondary)
                }
                HStack {
                    Spacer()
                    Button("Cancel") { exporting = false; exportPass = ""; exportPass2 = "" }
                    Button("Export…") { runExport() }
                        .keyboardShortcut(.defaultAction)
                        .disabled(exportPass.count < 6 || exportPass != exportPass2)
                }
            }
            .padding(18)
            .frame(width: 360)
        }
    }

    /// Ask where to save, then let the local server write the encrypted bundle.
    private func runExport() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "her-memory.ctwin-vault"
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let dest = panel.url else { return }
        guard let url = URL(string: "http://127.0.0.1:7878/api/vault/export"),
              let body = try? JSONSerialization.data(withJSONObject:
                    ["path": dest.path, "passphrase": exportPass]) else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        URLSession.shared.dataTask(with: req) { data, _, _ in
            let ok = (try? JSONSerialization.jsonObject(with: data ?? Data()) as? [String: Any])
                .flatMap { $0?["ok"] as? Bool } ?? false
            DispatchQueue.main.async {
                exportNote = ok ? "exported → \(dest.lastPathComponent)"
                               : "export failed — is the agent running?"
                exportPass = ""; exportPass2 = ""
            }
        }.resume()
    }
}
