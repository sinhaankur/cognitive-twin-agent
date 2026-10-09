import SwiftUI

/// The iOS Twin screen: the Siri orb, the answer, and an input bar. Mirrors the
/// macOS app's feel, sized for a phone. Speech can be added with iOS
/// SFSpeechRecognizer/AVSpeechSynthesizer (same as macOS); this is the typed core.
struct TwinView: View {
    @EnvironmentObject var model: TwinModel
    @State private var phase: CGFloat = 0
    @State private var typed = ""
    @State private var showPersona = false
    @State private var showBrain = false
    @State private var showSettings = false
    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            // dark Siri backdrop
            RadialGradient(colors: [Color(red: 0.08, green: 0.09, blue: 0.13), .black],
                           center: .top, startRadius: 0, endRadius: 700)
                .ignoresSafeArea()

            VStack(spacing: 18) {
                // One clean control on the top-right — a crafted menu with an
                // identity header and grouped items. A quiet reachability dot
                // sits to its left (parity with the macOS app's status dot), so
                // "can she be reached?" is answerable at a glance.
                HStack(spacing: 12) {
                    Spacer()
                    if let reachable = model.reachable {
                        HStack(spacing: 6) {
                            Circle()
                                .fill(reachable ? Color.green : Color.orange)
                                .frame(width: 7, height: 7)
                            Text(reachable ? "connected" : "unreachable")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(.white.opacity(0.5))
                        }
                        .transition(.opacity)
                    }
                    TopMenu(
                        name: model.personaName,
                        onWhoSheIs: { showPersona = true },
                        onHowSheThinks: { showBrain = true },
                        onSettings: { showSettings = true }
                    )
                }
                .padding(.horizontal)
                .padding(.top, 4)
                .animation(.easeInOut(duration: 0.25), value: model.reachable)

                Spacer()

                // The Siri-style orb — the original visual Ankur preferred.
                SiriOrb(amplitude: model.thinking ? 0.35 : 0.18,
                        phase: phase,
                        tint: Color(red: 0.30, green: 0.45, blue: 0.95),
                        portraitMesh: model.portraitMeshURL)
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
        .onAppear { model.refreshReachability() }
        .sheet(isPresented: $showPersona) { PersonaEditor().environmentObject(model) }
        .sheet(isPresented: $showBrain) { BrainView().environmentObject(model) }
        .sheet(isPresented: $showSettings, onDismiss: { model.refreshReachability() }) {
            SettingsView().environmentObject(model)
        }
    }

    private func send() {
        let t = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        typed = ""
        model.ask(t)
    }
}

// MARK: - Top menu
//
// The single top-right control. We take the *quality bar* of a great menu —
// an identity header, grouped items, quiet typography, restraint — but make it
// Vera's own: warm, dark, glass, matching the Siri orb's world. It is NOT a
// clone of anyone's settings list; it's a small, crafted sheet that belongs to
// this app. One tap opens it; a tap on a row does the thing and closes.

struct TopMenu: View {
    let name: String
    let onWhoSheIs: () -> Void
    let onHowSheThinks: () -> Void
    let onSettings: () -> Void

    @State private var open = false

    var body: some View {
        Button {
            withAnimation(.spring(response: 0.34, dampingFraction: 0.82)) { open = true }
        } label: {
            // A soft monogram chip, not a bare glyph — reads as "her", and as a
            // real affordance.
            Text(initial)
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .foregroundStyle(.white)
                .frame(width: 34, height: 34)
                .background(
                    Circle().fill(
                        LinearGradient(
                            colors: [Color(red: 0.34, green: 0.49, blue: 0.98),
                                     Color(red: 0.24, green: 0.33, blue: 0.80)],
                            startPoint: .topLeading, endPoint: .bottomTrailing
                        )
                    )
                )
                .overlay(Circle().strokeBorder(.white.opacity(0.18), lineWidth: 1))
                .shadow(color: .black.opacity(0.35), radius: 8, y: 3)
        }
        .accessibilityLabel("Menu")
        .sheet(isPresented: $open) {
            TopMenuSheet(
                name: name,
                onWhoSheIs: { close(onWhoSheIs) },
                onHowSheThinks: { close(onHowSheThinks) },
                onSettings: { close(onSettings) }
            )
            .presentationDetents([.height(340)])
            .presentationDragIndicator(.visible)
            .presentationBackground(.clear)
        }
    }

    private var initial: String {
        let t = name.trimmingCharacters(in: .whitespaces)
        return t.isEmpty || t == "Your twin" ? "✦" : String(t.prefix(1)).uppercased()
    }

    private func close(_ action: @escaping () -> Void) {
        open = false
        // Let the sheet dismiss before presenting the next one — avoids a
        // double-sheet flicker on iOS.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.32) { action() }
    }
}

private struct TopMenuSheet: View {
    let name: String
    let onWhoSheIs: () -> Void
    let onHowSheThinks: () -> Void
    let onSettings: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Identity header — who you're with, set warmly.
            HStack(spacing: 13) {
                Text(initial)
                    .font(.system(size: 20, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white)
                    .frame(width: 46, height: 46)
                    .background(
                        Circle().fill(
                            LinearGradient(
                                colors: [Color(red: 0.34, green: 0.49, blue: 0.98),
                                         Color(red: 0.24, green: 0.33, blue: 0.80)],
                                startPoint: .topLeading, endPoint: .bottomTrailing
                            )
                        )
                    )
                    .overlay(Circle().strokeBorder(.white.opacity(0.18), lineWidth: 1))
                VStack(alignment: .leading, spacing: 2) {
                    Text(displayName)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(.white)
                    Text("On this device · private")
                        .font(.system(size: 12.5))
                        .foregroundStyle(.white.opacity(0.5))
                }
                Spacer()
            }
            .padding(.horizontal, 18)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider().overlay(.white.opacity(0.08))

            // Grouped items.
            VStack(spacing: 0) {
                MenuRow(icon: "person.crop.circle", title: "Who she is",
                        subtitle: "Her persona & voice", action: onWhoSheIs)
                MenuRow(icon: "brain", title: "How she thinks",
                        subtitle: "See her mind", action: onHowSheThinks)
                MenuRow(icon: "gearshape", title: "Settings",
                        subtitle: "Model, privacy & more", action: onSettings)
            }
            .padding(.vertical, 6)

            Spacer(minLength: 0)
        }
        .background(
            // Vera's own surface: deep glass over the Siri-world navy, not a
            // flat system card.
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(.ultraThinMaterial)
                .environment(\.colorScheme, .dark)
                .overlay(
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .fill(Color(red: 0.08, green: 0.09, blue: 0.14).opacity(0.72))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .strokeBorder(.white.opacity(0.08), lineWidth: 1)
                )
        )
        .padding(.horizontal, 10)
        .padding(.bottom, 10)
    }

    private var displayName: String {
        name == "Your twin" ? "Your twin" : name
    }
    private var initial: String {
        let t = name.trimmingCharacters(in: .whitespaces)
        return t.isEmpty || t == "Your twin" ? "✦" : String(t.prefix(1)).uppercased()
    }
}

private struct MenuRow: View {
    let icon: String
    let title: String
    let subtitle: String
    let action: () -> Void
    @State private var pressed = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.white.opacity(0.85))
                    .frame(width: 26)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(.white)
                    Text(subtitle)
                        .font(.system(size: 12.5))
                        .foregroundStyle(.white.opacity(0.45))
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.25))
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 12)
            .background(pressed ? Color.white.opacity(0.06) : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onLongPressGesture(minimumDuration: 0, pressing: { pressed = $0 }, perform: {})
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
                ToolbarItem(placement: .cancellationAction) {
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
