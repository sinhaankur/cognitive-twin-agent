import Foundation

/// Talks to the local Cognitive Twin agent over its HTTP API (the same
/// `cognitive_twin.voice.server` we built and tested). Everything stays on
/// 127.0.0.1 — local-first, in the spirit of Unhosted.
struct AgentReply {
    let answer: String
    let model: String?
    let rule: String?
}

final class AgentClient {
    let baseURL: URL

    init(port: Int = 7878) {
        self.baseURL = URL(string: "http://127.0.0.1:\(port)")!
    }

    /// GET /api/health — returns true if the local agent server is reachable.
    func health() async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/health"))
        req.timeoutInterval = 4
        do {
            let (_, resp) = try await URLSession.shared.data(for: req)
            return (resp as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }

    /// GET /api/models — list installed local models.
    func models() async -> [String] {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/models"))
        req.timeoutInterval = 6
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            return (obj["models"] as? [String]) ?? []
        } catch {
            return []
        }
    }

    /// POST /api/speak — speak text aloud server-side, in the cloned voice if set
    /// up (falls back to the built-in voice). Returns true if it spoke as cloned.
    @discardableResult
    func speak(_ text: String) async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/speak"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text])
        req.timeoutInterval = 180
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            return (obj["cloned"] as? Bool) ?? false
        } catch { return false }
    }

    /// Is a cloned voice ready on the server?
    func cloneReady() async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/voice/clone/status"))
        req.timeoutInterval = 5
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            return (obj["ready"] as? Bool) ?? false
        } catch { return false }
    }

    /// POST /api/voice/add — teach Anita a loved one's voice from their writing.
    func addVoice(person: String, text: String) async -> Int {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/voice/add"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["person": person, "text": text])
        req.timeoutInterval = 15
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            return (obj["samples"] as? Int) ?? 0
        } catch { return 0 }
    }

    /// POST /api/remember — teach the twin a fact to keep (e.g. its own name).
    func remember(_ fact: String) async {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/remember"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["fact": fact])
        req.timeoutInterval = 6
        _ = try? await URLSession.shared.data(for: req)
    }

    /// POST /api/voice/clone — set a recording as the cloned voice (by file path).
    func setVoiceClone(path: String, person: String) async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/voice/clone"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["path": path, "person": person])
        req.timeoutInterval = 60
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            return (obj["ready"] as? Bool) ?? false
        } catch { return false }
    }

    /// GET /api/reflections — thoughts Anita had about your projects while away.
    func reflections() async -> [String] {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/reflections"))
        req.timeoutInterval = 6
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            let items = obj["items"] as? [[String: Any]] ?? []
            return items.compactMap { $0["thought"] as? String }
        } catch { return [] }
    }

    /// POST /api/reflect — have her think about your projects now; returns the thought.
    @discardableResult
    func reflect() async -> String? {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/reflect"))
        req.httpMethod = "POST"
        req.timeoutInterval = 120
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            if (obj["ok"] as? Bool) == true { return obj["thought"] as? String }
            return nil
        } catch { return nil }
    }

    /// POST /api/model — switch the active model. Returns true on success.
    func setModel(_ name: String) async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/model"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["model": name])
        req.timeoutInterval = 8
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
            return (obj["ok"] as? Bool) ?? false
        } catch {
            return false
        }
    }

    /// POST /api/memory/clear — wipe the local conversation memory.
    func clearMemory() async {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/memory/clear"))
        req.httpMethod = "POST"
        req.timeoutInterval = 6
        _ = try? await URLSession.shared.data(for: req)
    }

    /// POST /api/ask — send a transcript, get the agent's answer + route info.
    func ask(_ text: String) async throws -> AgentReply {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/ask"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["text": text])
        req.timeoutInterval = 120

        let (data, _) = try await URLSession.shared.data(for: req)
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        let answer = (obj["answer"] as? String) ?? "(no answer)"
        var model: String? = nil
        var rule: String? = nil
        if let route = obj["route"] as? [String: Any] {
            model = route["model"] as? String
            rule = route["rule"] as? String
        }
        return AgentReply(answer: answer, model: model, rule: rule)
    }
}
