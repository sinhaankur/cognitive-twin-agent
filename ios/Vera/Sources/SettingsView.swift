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
}
