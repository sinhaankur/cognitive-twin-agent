import SwiftUI
import Combine

/// OrbDriver — the app's ONE animation clock, in its OWN ObservableObject.
///
/// Why separate from AppModel: the orb's phase ticks ~24×/sec while she animates.
/// When those ticks lived as `@Published` scalars ON AppModel — the whole app's
/// `@EnvironmentObject` — every view observing the model (ChatPanel, FaceStrip,
/// the window) was invalidated on EVERY tick, cascading into a full SwiftUI view-
/// graph render. A `sample` showed `Published.subscript.getter` → `ViewGraphRoot…
/// render` burning ~25% CPU at idle, which starved inference and made her feel
/// "frozen / not awake". Moving the animation state into THIS tiny object means
/// only the orb views observe it — a phase tick redraws the orb and nothing else.
@MainActor
final class OrbDriver: ObservableObject {
    @Published var phase: CGFloat = 0
    @Published var springAmp: CGFloat = 0      // spring-tracked amplitude
    @Published var pulse: CGFloat = 0          // breathing pulse for "thought waiting"

    private var springVel: CGFloat = 0
    private var timer: Timer?
    private static let fps: Double = 24

    /// A source of the live drive signals (read each tick) — supplied by AppModel
    /// so the driver stays decoupled from it. Returns (targetAmplitude, isThinking,
    /// hasThoughtWaiting, decayVoicePulse).
    var signals: () -> (amp: CGFloat, thinking: Bool, thought: Bool, decayVoicePulse: () -> Void)
        = { (0, false, false, {}) }

    func start() {
        guard timer == nil else { return }
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / Self.fps, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.tick() }
        }
    }

    func stop() { timer?.invalidate(); timer = nil }

    private func tick() {
        let dt = CGFloat(1.0 / Self.fps)
        let s = signals()
        let target = s.amp
        // Only do work (and only PUBLISH) while something is actually moving — a
        // fully idle orb costs nothing and never invalidates a view.
        let moving = target > 0.001 || springAmp > 0.001 || abs(springVel) > 0.001
            || s.thinking || s.thought
        guard moving else { return }

        phase += (0.05 + springAmp * 0.30) * (60 * dt)
        pulse = (sin(phase * 0.9) + 1) / 2
        springVel += (target - springAmp) * 90 * dt
        springVel *= exp(-dt * 14)
        springAmp = max(0, springAmp + springVel * dt)
        s.decayVoicePulse()
    }
}
