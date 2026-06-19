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
