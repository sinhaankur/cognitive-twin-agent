import SwiftUI

/// iOS Settings & Privacy — the phone counterpart of the macOS SettingsView.
///
/// Deliberately a SUBSET shaped for a phone: there's no local Ollama / voice
/// installer here (those are desktop concerns), so this screen covers what a
/// phone actually needs — where the model runs, the opt-in 3D likeness, access
/// to the persona, and the privacy controls that back the core promise
/// ("inspect or wipe everything"). Every control binds to real TwinModel state.
struct SettingsView: View {
    @EnvironmentObject var model: TwinModel
    @Environment(\.dismiss) private var dismiss

    @State private var showPersona = false
    @State private var confirmClear = false
    @State private var probing = false
    @State private var reach: ReachResult?

    var body: some View {
        NavigationStack {
            Form {
                // ── Model host ────────────────────────────────────────────
                Section {
                    TextField("e.g. my-mac.tailnet.ts.net", text: $model.modelHost)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.body.monospaced())
                    TextField("Model", text: $model.modelName)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.body.monospaced())

                    // Verify she can actually be reached before you rely on it —
                    // a wrong host otherwise only shows up as a silent failure
                    // mid-conversation.
                    Button {
                        testConnection()
                    } label: {
                        HStack {
                            if probing {
                                ProgressView().controlSize(.small)
                                Text("Checking…")
                            } else {
                                Image(systemName: "dot.radiowaves.left.and.right")
                                Text("Test connection")
                            }
                        }
                    }
                    .disabled(probing)

                    if let reach {
                        HStack(spacing: 8) {
                            Image(systemName: reach.ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                .foregroundStyle(reach.ok ? .green : .orange)
                            Text(reach.message)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                } header: {
                    Text("Where she thinks")
                } footer: {
                    Text("A phone can't run the model itself. Point this at a machine you own that does — your Mac or home server running Ollama (e.g. my-mac.tailnet.ts.net, or host:port), reached privately over your Tailscale network. Leave blank to use localhost. Nothing is sent to a third party.")
                }

                // ── Her presence ──────────────────────────────────────────
                Section {
                    Toggle("Show her in 3D", isOn: $model.portrait3DEnabled)
                    Button {
                        showPersona = true
                    } label: {
                        Label("Who she is", systemImage: "person.text.rectangle")
                    }
                } header: {
                    Text("Presence")
                } footer: {
                    Text("The 3D likeness is built on your Mac and arrives with the memory vault; when it isn't present the orb is shown as always. “Who she is” is the persona that shapes how she speaks.")
                }

                // ── Privacy ───────────────────────────────────────────────
                Section {
                    HStack {
                        Label("Remembered", systemImage: "brain")
                        Spacer()
                        Text("\(model.memoryCount)")
                            .foregroundStyle(.secondary)
                            .font(.body.monospaced())
                    }
                    Button(role: .destructive) {
                        confirmClear = true
                    } label: {
                        Label("Forget everything she's learned", systemImage: "trash")
                    }
                    .disabled(model.memoryCount == 0)
                } header: {
                    Text("Privacy")
                } footer: {
                    Text("Everything stays on this phone — no account, no cloud, no telemetry. Clearing forgets the day-to-day topics she's picked up; her persona is kept.")
                }

                // ── About ─────────────────────────────────────────────────
                Section {
                    LabeledContent("App", value: "Vera · Cognitive Twin")
                    LabeledContent("Mode", value: "On-device · private")
                } footer: {
                    Text("An on-device twin of a loved one, in their voice — never cloud. Part of the Unhosted family.")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .sheet(isPresented: $showPersona) {
                PersonaEditor().environmentObject(model)
            }
            .confirmationDialog(
                "Forget everything she's learned?",
                isPresented: $confirmClear,
                titleVisibility: .visible
            ) {
                Button("Forget", role: .destructive) { model.clearMemory() }
                Button("Keep", role: .cancel) {}
            } message: {
                Text("This clears \(model.memoryCount) remembered item\(model.memoryCount == 1 ? "" : "s"). Her persona and 3D likeness are kept. This can't be undone.")
            }
        }
    }

    // MARK: - Reachability

    struct ReachResult { let ok: Bool; let message: String }

    /// A quick, honest check that the Ollama host is actually reachable — hits
    /// its root over HTTP (Ollama answers "Ollama is running"). Blank host →
    /// checks localhost, matching what the core would dial.
    private func testConnection() {
        probing = true
        reach = nil
        let raw = model.modelHost.trimmingCharacters(in: .whitespaces)
        let hostPort = raw.isEmpty ? "localhost:11434" : (raw.contains(":") ? raw : "\(raw):11434")
        guard let url = URL(string: "http://\(hostPort)/") else {
            reach = ReachResult(ok: false, message: "That host doesn’t look valid.")
            probing = false
            return
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = 6
        let started = Date()
        URLSession.shared.dataTask(with: req) { data, resp, err in
            let ms = Int(Date().timeIntervalSince(started) * 1000)
            DispatchQueue.main.async {
                probing = false
                if let err = err as NSError? {
                    reach = ReachResult(ok: false, message: Self.friendly(err))
                    return
                }
                let body = String(data: data ?? Data(), encoding: .utf8) ?? ""
                let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
                if body.lowercased().contains("ollama") || code == 200 {
                    reach = ReachResult(ok: true, message: "Reached \(hostPort) · \(ms) ms")
                } else {
                    reach = ReachResult(ok: false, message: "Answered, but doesn’t look like Ollama (HTTP \(code)).")
                }
            }
        }.resume()
    }

    private static func friendly(_ err: NSError) -> String {
        switch err.code {
        case NSURLErrorCannotConnectToHost, NSURLErrorCannotFindHost:
            return "Can’t reach that host. Is the machine on and Ollama running?"
        case NSURLErrorTimedOut:
            return "Timed out. Check you’re on the same tailnet."
        case NSURLErrorNotConnectedToInternet:
            return "No network. Connect to your tailnet and retry."
        default:
            return "Couldn’t connect (\(err.localizedDescription))."
        }
    }
}
