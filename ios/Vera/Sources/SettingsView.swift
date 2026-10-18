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
    @ObservedObject private var voice = Voice.shared

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

                    // The seamless path: find your Mac on the tailnet for you, so
                    // you never have to type an address. This is what most people
                    // should tap first.
                    Button {
                        reach = nil
                        model.autoDetect()
                    } label: {
                        HStack {
                            if model.autoDetecting {
                                ProgressView().controlSize(.small)
                                Text("Looking for your Mac…")
                            } else {
                                Image(systemName: "wand.and.stars")
                                Text("Connect automatically")
                            }
                        }
                    }
                    .disabled(model.autoDetecting)

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
                                .foregroundStyle(reach.ok ? VeraTokens.accent : VeraTokens.warn)
                            Text(reach.message)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                } header: {
                    Text("Where she thinks")
                } footer: {
                    Text("A phone can't run the model itself, so she thinks on your Mac. Tap **Connect automatically** and she'll find it over Tailscale — no address to type. Use your Mac's Tailscale name (ends in .ts.net), not its 100.x number: iPhones block plain numbers for safety. Everything stays between your devices; nothing is sent to a third party.")
                }

                // ── How to connect (plain-language help) ──────────────────
                Section {
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 10) {
                            connectStep("1", "On your Mac, open the Vera app and leave it running — that's where she thinks.")
                            connectStep("2", "Make sure Tailscale is on, signed in with the same account, on both the Mac and this phone. It's a private, encrypted link between your own devices — nothing public.")
                            connectStep("3", "Back here, tap **Connect automatically**. She'll find your Mac by its name and remember it.")
                            connectStep("4", "If it can't find her, open the Mac's menu-bar Tailscale, copy its name (ends in .ts.net), and paste it above.")
                        }
                        .padding(.vertical, 4)
                    } label: {
                        Label("How do I connect?", systemImage: "questionmark.circle")
                    }
                } footer: {
                    Text("Tailscale is a free, private network just for the machines you own. Your Mac and phone talk directly, encrypted end-to-end — the way a loved one's words should stay.")
                }

                // ── Her presence ──────────────────────────────────────────
                Section {
                    Toggle("Speak her replies aloud", isOn: $voice.enabled)
                    Toggle("Show her in 3D", isOn: $model.portrait3DEnabled)
                    Button {
                        showPersona = true
                    } label: {
                        Label("Who she is", systemImage: "person.text.rectangle")
                    }
                } header: {
                    Text("Presence")
                } footer: {
                    Text("Her voice is spoken on this phone, entirely on-device — no audio ever leaves it. The 3D likeness is built on your Mac and arrives with the memory vault; when it isn't present the orb is shown as always. “Who she is” is the persona that shapes how she speaks.")
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

    // MARK: - Connect help

    /// One numbered step in the "How do I connect?" guide.
    private func connectStep(_ n: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(n)
                .font(.caption.bold().monospaced())
                .foregroundStyle(.white)
                .frame(width: 20, height: 20)
                .background(Circle().fill(VeraTokens.accent))
            Text(.init(text))  // markdown-aware for **bold**
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
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
        // The "requires a secure connection" block: iOS refused a plain-number
        // (100.x) address. Point them at the fix — use the Mac's Tailscale name.
        let desc = err.localizedDescription.lowercased()
        if desc.contains("secure connection") || desc.contains("app transport") ||
           (err.domain == NSURLErrorDomain && err.code == NSURLErrorAppTransportSecurityRequiresSecureConnection) {
            return "Use your Mac's Tailscale name (ends in .ts.net), not its 100.x number — iPhones block plain numbers. Tap “Connect automatically”."
        }
        switch err.code {
        case NSURLErrorCannotConnectToHost, NSURLErrorCannotFindHost:
            return "Can’t reach that host. Is your Mac on, with the Vera app and Ollama running?"
        case NSURLErrorTimedOut:
            return "Timed out. Check Tailscale is on, same account, on both devices."
        case NSURLErrorNotConnectedToInternet:
            return "No network. Connect to your tailnet and retry."
        default:
            return "Couldn’t connect (\(err.localizedDescription))."
        }
    }
}
