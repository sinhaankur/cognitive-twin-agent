import AppIntents
import Foundation

/// Siri + Shortcuts integration via App Intents.
///
/// Lets you say "Hey Siri, ask Anita …" (or run it from Shortcuts / Spotlight),
/// send a question to the local twin, and have Siri speak her reply back. Uses
/// the same local agent server — nothing leaves the machine.
@available(macOS 13.0, iOS 16.0, *)
struct AskAnitaIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Anita"
    static var description = IntentDescription(
        "Ask your twin a question and hear the answer — answered locally on your device."
    )
    // Speak the result back through Siri.
    static var openAppWhenRun: Bool = false

    @Parameter(title: "Question", requestValueDialog: "What would you like to ask?")
    var question: String

    static var parameterSummary: some ParameterSummary {
        Summary("Ask Anita \(\.$question)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let agent = AgentClient()
        // Make sure the local agent is reachable; if not, say so plainly.
        guard await agent.health() else {
            return .result(dialog: "Anita isn't running yet. Open the app and try again.")
        }
        do {
            let reply = try await agent.ask(question)
            return .result(dialog: IntentDialog(stringLiteral: reply.answer))
        } catch {
            return .result(dialog: "Sorry, I couldn't reach Anita just now.")
        }
    }
}

/// A second intent: open Anita's chat panel.
@available(macOS 13.0, iOS 16.0, *)
struct OpenAnitaIntent: AppIntent {
    static var title: LocalizedStringResource = "Open Anita"
    static var description = IntentDescription("Bring up your twin.")
    static var openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        return .result()
    }
}

/// Phrases Siri recognizes, and Shortcuts suggestions.
@available(macOS 13.0, iOS 16.0, *)
struct AnitaShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AskAnitaIntent(),
            phrases: [
                "Ask \(.applicationName)",
                "Ask \(.applicationName) a question",
                "Talk to \(.applicationName)",
            ],
            shortTitle: "Ask Anita",
            systemImageName: "bubble.left.and.bubble.right"
        )
        AppShortcut(
            intent: OpenAnitaIntent(),
            phrases: ["Open \(.applicationName)"],
            shortTitle: "Open Anita",
            systemImageName: "circle.hexagongrid.fill"
        )
    }
}
