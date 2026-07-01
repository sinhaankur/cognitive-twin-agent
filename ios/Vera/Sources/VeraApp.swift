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

    func savePersona(_ json: String) {
        personaJSON = json
        UserDefaults.standard.set(json, forKey: "persona")
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
