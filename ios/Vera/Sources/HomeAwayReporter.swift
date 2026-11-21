import Combine
import CoreLocation
import Foundation
import Network

/// HomeAwayReporter — your phone tells Vera when you come home and when you leave.
///
/// The Mac can only see so much; the phone is what actually travels with you. So
/// this quietly reports your home/away belief to her brain (the voice server on
/// the Mac, :7878 → /api/homeaway/report), and she greets you / goes quiet.
///
/// How it decides, cheapest-first (same spirit as the brain's homeaway.py):
///   • On Wi-Fi AND her brain is reachable on the LAN  → you're HOME.
///   • Off Wi-Fi (cellular) or brain unreachable        → you're AWAY.
///   • If you grant Location, it ALSO sends coarse coords so the brain's geofence
///     can confirm — the "track movement if needed" escalation, opt-in only.
///
/// Nothing goes to a third party: the report posts to YOUR Mac over your own
/// network / Tailscale. No background location unless you allow it; no trail kept.
@MainActor
final class HomeAwayReporter: NSObject, ObservableObject {
    @Published var lastBelief: Bool? = nil        // true home · false away · nil unknown
    @Published var enabled: Bool = UserDefaults.standard.bool(forKey: "homeawayEnabled") {
        didSet {
            UserDefaults.standard.set(enabled, forKey: "homeawayEnabled")
            if enabled { start() } else { stop() }
        }
    }

    /// Where her brain lives — the Mac host. Reuses the same host the model uses,
    /// but the brain's voice server is on 7878 (Ollama is 11434).
    var hostProvider: () -> String = { UserDefaults.standard.string(forKey: "modelHost") ?? "" }

    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "vera.homeaway.path")
    private let locationManager = CLLocationManager()
    private var onWiFi = false
    private var lastSent: Bool? = nil
    private var lastSentAt = Date.distantPast

    override init() {
        super.init()
        locationManager.delegate = self
        locationManager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        if enabled { start() }
    }

    func start() {
        monitor.pathUpdateHandler = { [weak self] path in
            let wifi = path.usesInterfaceType(.wifi) && path.status == .satisfied
            Task { @MainActor in self?.wifiChanged(wifi) }
        }
        monitor.start(queue: queue)
    }

    func stop() {
        monitor.cancel()
        locationManager.stopMonitoringSignificantLocationChanges()
    }

    /// Ask for the optional "track movement" location permission (geofence confirm).
    func enableLocation() {
        locationManager.requestWhenInUseAuthorization()
        locationManager.startMonitoringSignificantLocationChanges()
    }

    private func wifiChanged(_ wifi: Bool) {
        onWiFi = wifi
        reassess()
    }

    /// Decide home/away and, if it changed (or it's been a while), report it.
    private func reassess() {
        // On Wi-Fi, confirm the brain actually answers — being on *some* Wi-Fi isn't
        // home; being on YOUR network (where her brain lives) is.
        if onWiFi {
            pingBrain { [weak self] reachable in
                self?.setBelief(reachable)        // on home LAN ⇒ home
            }
        } else {
            setBelief(false)                      // cellular / no Wi-Fi ⇒ out
        }
    }

    private func setBelief(_ home: Bool) {
        lastBelief = home
        // Debounce the network: only POST on a change, or every ~5 min as a refresh
        // (the brain treats reports older than 15 min as stale).
        let changed = (home != lastSent)
        let stale = Date().timeIntervalSince(lastSentAt) > 300
        guard changed || stale else { return }
        lastSent = home
        lastSentAt = Date()
        report(home: home, coords: nil)
    }

    private func pingBrain(_ done: @escaping (Bool) -> Void) {
        guard let url = brainURL(path: "/api/health") else { done(false); return }
        var req = URLRequest(url: url)
        req.timeoutInterval = 4
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            let ok = (resp as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { done(ok) }
        }.resume()
    }

    private func report(home: Bool, coords: CLLocationCoordinate2D?) {
        guard enabled, let url = brainURL(path: "/api/homeaway/report") else { return }
        var body: [String: Any] = ["device": deviceName(), "home": home]
        if let c = coords { body["lat"] = c.latitude; body["lon"] = c.longitude }
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        req.timeoutInterval = 6
        URLSession.shared.dataTask(with: req).resume()
    }

    /// The brain's voice server (port 7878) on the configured Mac host.
    private func brainURL(path: String) -> URL? {
        let raw = hostProvider().trimmingCharacters(in: .whitespaces)
        guard !raw.isEmpty else { return nil }
        // strip any :port the user typed (that's Ollama's); the brain is on 7878.
        let host = raw.split(separator: ":").first.map(String.init) ?? raw
        return URL(string: "http://\(host):7878\(path)")
    }

    private func deviceName() -> String {
        #if canImport(UIKit)
        return "iphone"
        #else
        return "phone"
        #endif
    }
}

extension HomeAwayReporter: CLLocationManagerDelegate {
    nonisolated func locationManager(_ manager: CLLocationManager,
                                     didUpdateLocations locations: [CLLocation]) {
        guard let c = locations.last?.coordinate else { return }
        Task { @MainActor in
            // Send coarse coords alongside the current belief so the brain's geofence
            // can confirm — only ever when the user turned Location on.
            self.report(home: self.lastBelief ?? false, coords: c)
        }
    }
}
