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

    // Can she actually be reached right now? Parity with the macOS app, which
    // shows a live green/orange dot. nil = unknown (not yet checked / no host).
    @Published var reachable: Bool? = nil

    /// Quietly check whether the model host answers. Mirrors the macOS health
    /// watchdog; called on appear and after a host change. Never blocks the UI.
    func refreshReachability() {
        let raw = modelHost.trimmingCharacters(in: .whitespaces)
        // No host set → try to AUTO-DETECT over Tailscale before giving up.
        guard !raw.isEmpty else {
            reachable = nil
            autoDetect()
            return
        }
        let hostPort = raw.contains(":") ? raw : "\(raw):11434"
        guard let url = URL(string: "http://\(hostPort)/") else { reachable = false; return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 5
        URLSession.shared.dataTask(with: req) { data, resp, err in
            let ok = err == nil &&
                ((resp as? HTTPURLResponse)?.statusCode == 200 ||
                 (String(data: data ?? Data(), encoding: .utf8) ?? "").lowercased().contains("ollama"))
            DispatchQueue.main.async {
                self.reachable = ok
                // if the saved host stopped answering, try to re-discover it
                if !ok { self.autoDetect() }
            }
        }.resume()
    }

    @Published var autoDetecting = false

    /// SEAMLESS CONNECT: find the Mac's Ollama on your Tailscale automatically, so
    /// you never type an IP. Probes a few likely candidates in parallel — the Mac's
    /// MagicDNS name and the Tailscale 100.x host range — and the first that answers
    /// "Ollama is running" becomes the model host. Entirely private (your own
    /// tailnet); a no-op if nothing answers (you can still type it in Settings).
    func autoDetect() {
        guard !autoDetecting else { return }
        // only auto-detect when there's no working host yet
        if !modelHost.trimmingCharacters(in: .whitespaces).isEmpty && reachable == true { return }
        autoDetecting = true

        // candidates, most-likely first: hosts you've reached before (remembered via
        // MagicDNS or IP), then the Mac's Tailscale MagicDNS name. MagicDNS resolves
        // on-device when Tailscale is up, so a hostname is the reliable, IP-free path.
        var candidates: [String] = []
        if let saved = UserDefaults.standard.stringArray(forKey: "knownHosts") { candidates += saved }
        // the Mac's MagicDNS name (works across IP changes). The user can override the
        // hostname via "veraMacHost"; default to the known machine name.
        let macName = UserDefaults.standard.string(forKey: "veraMacHost")
            ?? "ankursinhas-macbook-pro-1.tail2d11a0.ts.net"
        candidates.append(macName)
        candidates.append("100.91.27.70")           // last-known Mac Tailscale IP
        let unique = Array(NSOrderedSet(array: candidates).array as? [String] ?? candidates).prefix(10)

        let group = DispatchGroup()
        var found: String?
        let lock = NSLock()
        for host in unique {
            guard let url = URL(string: "http://\(host):11434/") else { continue }
            group.enter()
            var req = URLRequest(url: url); req.timeoutInterval = 2
            URLSession.shared.dataTask(with: req) { data, resp, err in
                defer { group.leave() }
                let ok = err == nil &&
                    ((String(data: data ?? Data(), encoding: .utf8) ?? "").lowercased().contains("ollama"))
                if ok { lock.lock(); if found == nil { found = host }; lock.unlock() }
            }.resume()
        }
        group.notify(queue: .main) {
            self.autoDetecting = false
            if let h = found {
                self.modelHost = h
                self.reachable = true
                var known = UserDefaults.standard.stringArray(forKey: "knownHosts") ?? []
                if !known.contains(h) { known.insert(h, at: 0); UserDefaults.standard.set(Array(known.prefix(5)), forKey: "knownHosts") }
            }
        }
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
        // Tell the Rust core where the model lives (a machine you own on your
        // tailnet). The core reads CTWIN_OLLAMA_HOST; empty → it uses its
        // localhost default, so nothing breaks when the host isn't set yet.
        let host = modelHost.trimmingCharacters(in: .whitespaces)
        if host.isEmpty {
            unsetenv("CTWIN_OLLAMA_HOST")
        } else {
            setenv("CTWIN_OLLAMA_HOST", host, 1)
        }
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
