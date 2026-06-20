import AppIntents
import Foundation

/// Siri + Shortcuts on iOS — "Hey Siri, ask Anita …". Runs the twin through the
/// shared Rust core (TwinCore), so it works on the phone without a server.
@available(iOS 16.0, *)
struct AskAnitaIntent: AppIntent {
    static var title: LocalizedStringResource = "Ask Anita"
    static var description = IntentDescription(
        "Ask your twin a question and hear the answer — on-device."
    )

    @Parameter(title: "Question", requestValueDialog: "What would you like to ask?")
    var question: String

    static var parameterSummary: some ParameterSummary {
        Summary("Ask Anita \(\.$question)")
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        // Persona + model come from the same place the app uses.
        let personaJSON = UserDefaults.standard.string(forKey: "persona")
            ?? #"{"name":"Anita"}"#
        let model = UserDefaults.standard.string(forKey: "model") ?? "qwen2.5:3b"
        let answer = await TwinCore.ask(
            model: model, personaJSON: personaJSON,
            recentPrompts: [], userInput: question
        )
        let text = answer.isEmpty ? "Sorry, I couldn't answer that right now." : answer
        return .result(dialog: IntentDialog(stringLiteral: text))
    }
}

@available(iOS 16.0, *)
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
    }
}
