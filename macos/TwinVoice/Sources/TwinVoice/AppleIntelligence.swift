import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

/// Apple Intelligence backend — the most local, most private option: Apple's
/// on-device foundation model running on the Neural Engine via the
/// FoundationModels framework. No Ollama, no network.
///
/// Gracefully reports unavailability when the framework or the model isn't
/// present (older macOS, Apple Intelligence off, unsupported hardware), so the
/// app simply falls back to the Ollama-backed local agent.
@MainActor
final class AppleIntelligence {

    /// Is Apple Intelligence usable right now on this machine?
    static var isAvailable: Bool {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            return SystemLanguageModel.default.availability == .available
        }
        return false
        #else
        return false
        #endif
    }

    /// A human-readable reason when it's not available (for settings UI).
    static var statusText: String {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available:
                return "Apple Intelligence: available (on-device)"
            case .unavailable(let reason):
                return "Apple Intelligence: unavailable (\(reason))"
            @unknown default:
                return "Apple Intelligence: unknown state"
            }
        }
        return "Apple Intelligence: needs macOS 26+"
        #else
        return "Apple Intelligence: framework not built in"
        #endif
    }

    // Stored untyped (stored properties can't be @available-gated); cast on use.
    private var sessionBox: Any?

    /// Answer a prompt fully on-device. Throws if AI isn't available.
    func ask(_ prompt: String, persona: String?) async throws -> String {
        #if canImport(FoundationModels)
        if #available(macOS 26.0, *) {
            let s: LanguageModelSession
            if let existing = sessionBox as? LanguageModelSession {
                s = existing
            } else {
                // Seed the session with the twin persona so it answers in voice.
                let instructions = persona ?? "You are a concise, local-first personal assistant."
                s = LanguageModelSession(instructions: instructions)
                sessionBox = s
            }
            let response = try await s.respond(to: prompt)
            return response.content
        }
        throw AIError.unavailable
        #else
        throw AIError.unavailable
        #endif
    }

    func reset() {
        sessionBox = nil
    }

    enum AIError: Error, LocalizedError {
        case unavailable
        var errorDescription: String? {
            "Apple Intelligence isn't available on this Mac."
        }
    }
}
