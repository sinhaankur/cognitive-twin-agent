import Foundation

/// Swift wrapper over the Rust core's C ABI (CognitiveTwinCore.xcframework).
/// This is the entire bridge between the iOS app and the portable Rust brain —
/// the same core that runs on macOS and the web.
///
/// Requires the xcframework added to the target and a bridging header that does:
///     #include "cognitive_twin_core.h"
enum TwinCore {

    /// Helper: call a C function that returns an owned `char *`, copy to a Swift
    /// String, and free the Rust allocation.
    private static func takeString(_ ptr: UnsafeMutablePointer<CChar>?) -> String {
        guard let ptr else { return "" }
        defer { ctwin_string_free(ptr) }
        return String(cString: ptr)
    }

    /// Compile a persona into its system-prompt block.
    static func personaPrompt(personaJSON: String) -> String {
        takeString(ctwin_persona_prompt(personaJSON))
    }

    /// Build the full system prompt (base + persona + memory summary).
    static func systemPrompt(base: String, personaJSON: String, recentPrompts: [String]) -> String {
        let recents = (try? JSONEncoder().encode(recentPrompts)).flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
        return takeString(ctwin_system_prompt(base, personaJSON, recents))
    }

    /// Route a prompt against a policy; returns the decoded decision.
    static func route(policyJSON: String, prompt: String, device: String = "") -> [String: String] {
        let json = takeString(ctwin_route(policyJSON, prompt, device))
        guard let data = json.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: String]
        else { return [:] }
        return obj
    }

    /// Run one full agent turn against a local Ollama model. The single call the
    /// app needs to talk to the twin. Runs the Rust core on a background thread.
    static func ask(model: String, personaJSON: String, recentPrompts: [String],
                    userInput: String) async -> String {
        let recents = (try? JSONEncoder().encode(recentPrompts)).flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
        return await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let answer = takeString(ctwin_ask(model, personaJSON, recents, userInput))
                cont.resume(returning: answer)
            }
        }
    }
}
