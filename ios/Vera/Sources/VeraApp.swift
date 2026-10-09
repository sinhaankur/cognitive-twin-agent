import SwiftUI

/// iOS app entry. Same Cognitive Twin, on your phone — powered by the shared Rust
/// core (CognitiveTwinCore.xcframework) via TwinCore. The Siri orb is the same
/// pure-SwiftUI view used on macOS.
@main
struct VeraApp: App {
    @StateObject private var model = TwinModel()
    var body: some Scene {
        WindowGroup {
            TwinView().environmentObject(model)
        }
    }
}

/// iOS-side state. On a phone there's no local Ollama, so the model host is
/// configurable (point it at your Mac/home server running Ollama). The agent
/// brain (persona, memory, routing, prompt assembly) is the Rust core.
@MainActor
final class TwinModel: ObservableObject {
    @Published var transcript = ""
    @Published var answer = ""
    @Published var thinking = false
    @Published var modelName = "qwen2.5:3b"

    // Where the model runs. A phone has no local Ollama, so this points at a
    // machine you own that does (your Mac / home server) — persisted so it
    // survives restarts. Empty = not yet configured. Local-network only by
    // intent; nothing is sent to a third party.
    @Published var modelHost: String = UserDefaults.standard.string(forKey: "modelHost") ?? "" {
        didSet { UserDefaults.standard.set(modelHost, forKey: "modelHost") }
    }

    // The persona is created/edited by the user; persisted locally (UserDefaults
    // here for simplicity — the Rust core compiles it identically to desktop).
    @Published var personaJSON: String =
        UserDefaults.standard.string(forKey: "persona") ??
        #"{"name":"","likes":[],"dislikes":[],"values":[]}"#

    // Local prompt history — persisted so the twin's "learned" topics survive
    // restarts (kept small + on-device only, never sent anywhere).
    private var history: [String] = UserDefaults.standard.stringArray(forKey: "history") ?? []

    /// Read-only view of recent prompts, for the Brain graph.
    var recentPrompts: [String] { history }

    /// Her name, parsed from the persona — for the menu identity header. Falls
    /// back to a gentle default when no persona name is set yet.
    var personaName: String {
        guard let data = personaJSON.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let name = obj["name"] as? String,
              !name.trimmingCharacters(in: .whitespaces).isEmpty
        else { return "Your twin" }
        return name
    }

    // "See a loved one in 3D" — opt-in, persisted. On a phone there's no local
    // Blender pipeline, so the USDZ likeness is *built on your Mac* and arrives
    // with the memory vault (or dropped into the app's Documents). We only ever
    // display a face that's actually present; otherwise the orb is untouched.
    @Published var portrait3DEnabled = UserDefaults.standard.bool(forKey: "portrait3DOn") {
        didSet { UserDefaults.standard.set(portrait3DEnabled, forKey: "portrait3DOn") }
    }

    /// The likeness file, or nil. nil keeps the orb exactly as it always was.
    var portraitMeshURL: URL? {
        guard portrait3DEnabled else { return nil }
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
        let url = docs?.appendingPathComponent("portrait/face.usdz")
        if let url, FileManager.default.fileExists(atPath: url.path) { return url }
        return nil
    }

    func savePersona(_ json: String) {
        personaJSON = json
        UserDefaults.standard.set(json, forKey: "persona")
    }

    /// How many prompts she's learned from — shown in Settings so "clear" is
    /// never a mystery action.
    var memoryCount: Int { history.count }

    /// Forget the learned prompt history. The privacy promise ("inspect or wipe
    /// everything") made real on the phone. Persona + portrait are left alone;
    /// this only clears the day-to-day learned topics.
    func clearMemory() {
        history.removeAll()
        UserDefaults.standard.removeObject(forKey: "history")
        objectWillChange.send()
    }

    func ask(_ text: String) {
        transcript = text
        answer = ""
        thinking = true
        Task {
            let reply = await TwinCore.ask(
                model: modelName,
                personaJSON: personaJSON,
                recentPrompts: history,
                userInput: text
            )
            await MainActor.run {
                self.answer = reply
                self.thinking = false
                self.history.append(text)
                if self.history.count > 200 { self.history.removeFirst(self.history.count - 200) }
                UserDefaults.standard.set(self.history, forKey: "history")
            }
        }
    }
}
