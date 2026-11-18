// PrivacyClient — the menu bar's one link to Vera's brain: the /api/privacy
// endpoint (see cognitive_twin/voice/server.py). Reading it never needs the model,
// so the menu stays responsive even while the brain is busy — and when the brain
// is DOWN, we show "offline" instead of a hang. All loopback; never off-box.
//
// This mirrors Tailscale's own design: the menu is a thin native face over a
// local service. The Swift app launches instantly and costs almost nothing idle.

import Foundation

/// The whole control-surface state, matching privacy.explain() on the server.
struct PrivacyState: Codable, Equatable {
    var reach: String            // "private" | "my_devices"
    var reachLabel: String
    var whoCanReach: String
    var tokenSet: Bool
    var locked: Bool
    var lockdownNote: String
    var safeMode: Bool
    var safeModeNote: String
    var bindHost: String

    enum CodingKeys: String, CodingKey {
        case reach
        case reachLabel = "reach_label"
        case whoCanReach = "who_can_reach"
        case tokenSet = "token_set"
        case locked
        case lockdownNote = "lockdown_note"
        case safeMode = "safe_mode"
        case safeModeNote = "safe_mode_note"
        case bindHost = "bind_host"
    }

    /// Tailscale's "Connected" = reachable by your devices (and not locked down).
    var connected: Bool { reach == "my_devices" && !locked }

    /// A safe placeholder used when the brain can't be reached yet.
    static let offline = PrivacyState(
        reach: "private", reachLabel: "🔒 Private (this Mac only)",
        whoCanReach: "Only this Mac.", tokenSet: false, locked: false,
        lockdownNote: "", safeMode: true,
        safeModeNote: "Safe Mode is on.", bindHost: "127.0.0.1")
}

@MainActor
final class PrivacyClient: ObservableObject {
    @Published var state: PrivacyState = .offline
    @Published var online: Bool = false

    private let base: URL
    private var timer: Timer?

    init(port: Int = 7878) {
        self.base = URL(string: "http://127.0.0.1:\(port)")!
    }

    /// Poll the brain every few seconds so the menu is always honest — exactly how
    /// Tailscale's menu reflects live state. Light: one tiny GET, loopback.
    func start() {
        Task { await refresh() }
        timer = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
            Task { await self?.refresh() }
        }
    }

    func stop() { timer?.invalidate(); timer = nil }

    func refresh() async {
        guard let s = await get("/api/privacy") else {
            online = false
            return
        }
        online = true
        state = s
    }

    // ── actions (each posts one explicit change; the server logs it) ───────────

    /// The big Connect toggle: Private ⇄ My devices, like Tailscale's switch.
    func toggleConnect() async {
        await post(["reach": state.connected ? "private" : "my_devices"])
    }

    func setReach(_ reach: String) async { await post(["reach": reach]) }
    func setSafeMode(_ on: Bool) async { await post(["safe_mode": on]) }
    func rotateToken() async { await post(["rotate_token": true]) }

    /// Kill switch lives on /api/lockdown (already in the server).
    func setLockdown(_ on: Bool) async {
        await postTo("/api/lockdown", ["on": on])
        await refresh()
    }

    // ── tiny HTTP helpers (loopback only) ──────────────────────────────────────

    private func get(_ path: String) async -> PrivacyState? {
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.timeoutInterval = 3
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            return try JSONDecoder().decode(PrivacyState.self, from: data)
        } catch { return nil }
    }

    private func post(_ body: [String: Any]) async {
        await postTo("/api/privacy", body)
        await refresh()
    }

    private func postTo(_ path: String, _ body: [String: Any]) async {
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.timeoutInterval = 3
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        _ = try? await URLSession.shared.data(for: req)
    }
}
