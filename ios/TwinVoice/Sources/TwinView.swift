import SwiftUI

/// The iOS Twin screen: the Siri orb, the answer, and an input bar. Mirrors the
/// macOS app's feel, sized for a phone. Speech can be added with iOS
/// SFSpeechRecognizer/AVSpeechSynthesizer (same as macOS); this is the typed core.
struct TwinView: View {
    @EnvironmentObject var model: TwinModel
    @State private var phase: CGFloat = 0
    @State private var typed = ""
    @State private var showPersona = false
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            // dark Siri backdrop
            RadialGradient(colors: [Color(red: 0.08, green: 0.09, blue: 0.13), .black],
                           center: .top, startRadius: 0, endRadius: 700)
                .ignoresSafeArea()

            VStack(spacing: 18) {
                HStack {
                    Spacer()
                    Button { showPersona = true } label: {
                        Image(systemName: "person.crop.circle")
                            .font(.title2).foregroundStyle(.white.opacity(0.7))
                    }
                }
                .padding(.horizontal)

                Spacer()

                SiriOrb(amplitude: model.thinking ? 0.35 : 0.18,
                        phase: phase,
                        tint: Color(red: 0.30, green: 0.45, blue: 0.95))
                    .frame(width: 220, height: 220)

                if !model.transcript.isEmpty {
                    Text(model.transcript)
                        .font(.headline).foregroundStyle(.white)
                        .multilineTextAlignment(.center).padding(.horizontal)
                }

                ScrollView {
                    Text(model.answer)
                        .font(.body).foregroundStyle(.white.opacity(0.85))
                        .multilineTextAlignment(.center).padding(.horizontal)
                        .frame(maxWidth: .infinity)
                }
                .frame(maxHeight: 200)

                Spacer()

                HStack(spacing: 10) {
                    TextField("Ask your twin…", text: $typed)
                        .textFieldStyle(.plain)
                        .foregroundStyle(.white)
                        .padding(.vertical, 12).padding(.horizontal, 16)
                        .onSubmit(send)
                    Button(action: send) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 30))
                            .foregroundStyle(Color.accentColor)
                    }
                    .padding(.trailing, 6)
                }
                .background(Capsule().fill(.ultraThinMaterial))
                .padding(.horizontal)
                .padding(.bottom, 8)
            }
        }
        .onReceive(timer) { _ in phase += 0.06 + (model.thinking ? 0.2 : 0) }
        .sheet(isPresented: $showPersona) { PersonaEditor().environmentObject(model) }
    }

    private func send() {
        let t = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        typed = ""
        model.ask(t)
    }
}

/// Minimal persona creation on iOS — the user shapes who their twin is. Stored
/// locally and compiled by the Rust core, identically to desktop.
struct PersonaEditor: View {
    @EnvironmentObject var model: TwinModel
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var likes = ""
    @State private var dislikes = ""
    @State private var values = ""

    var body: some View {
        NavigationView {
            Form {
                Section("Who is your twin?") {
                    TextField("Your name", text: $name)
                    TextField("Likes (comma-separated)", text: $likes)
                    TextField("Dislikes (comma-separated)", text: $dislikes)
                    TextField("Values (comma-separated)", text: $values)
                }
                Section {
                    Text("Stored on this device. Your twin reasons as you.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Persona")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save(); dismiss() }
                }
                ToolbarItem(placement: .cancelAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .onAppear(perform: load)
    }

    private func list(_ s: String) -> [String] {
        s.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }

    private func save() {
        let obj: [String: Any] = [
            "name": name,
            "likes": list(likes),
            "dislikes": list(dislikes),
            "values": list(values),
        ]
        if let data = try? JSONSerialization.data(withJSONObject: obj),
           let json = String(data: data, encoding: .utf8) {
            model.savePersona(json)
        }
    }

    private func load() {
        guard let data = model.personaJSON.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }
        name = obj["name"] as? String ?? ""
        likes = (obj["likes"] as? [String] ?? []).joined(separator: ", ")
        dislikes = (obj["dislikes"] as? [String] ?? []).joined(separator: ", ")
        values = (obj["values"] as? [String] ?? []).joined(separator: ", ")
    }
}
