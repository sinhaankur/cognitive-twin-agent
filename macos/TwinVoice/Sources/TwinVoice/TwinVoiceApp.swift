import SwiftUI
import AppKit
import Foundation

@main
struct TwinVoiceApp: App {
    @StateObject private var model = AppModel()
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup("Twin Voice") {
            ContentView()
                .environmentObject(model)
                .frame(minWidth: 420, idealWidth: 480, maxWidth: 720,
                       minHeight: 560, idealHeight: 640, maxHeight: 900)
                .background(VisualEffectBackground())   // native translucent "glass"
                .onAppear { model.start() }
        }
        // A real, titled, movable window (keeps the title bar + traffic lights, but
        // we make the bar transparent so the glass shows through — a proper app
        // window, not a chrome-less floating panel).
        .windowResizability(.contentSize)
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unifiedCompact)
        .commands {
            CommandGroup(replacing: .newItem) {}   // no "New Window" — single window app
        }
    }
}

/// App-level setup so it behaves like a proper Mac app: shows in the Dock,
/// activates on launch, centers its window, and quits when the window closes.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)        // Dock icon + menu bar
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.async {
            if let w = NSApp.windows.first {
                w.titlebarAppearsTransparent = true
                w.titleVisibility = .hidden
                w.isMovableByWindowBackground = true   // drag anywhere to move
                w.center()
                w.makeKeyAndOrderFront(nil)
            }
        }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

/// Owns the agent server lifecycle, the voice engine, and the conversation state.
@MainActor
final class AppModel: ObservableObject {
    enum Phase: String { case idle, listening, thinking, speaking }

    @Published var phase: Phase = .idle
    @Published var transcript = ""
    @Published var answer = ""
    @Published var modelName = "…"
    @Published var serverUp = false

    let voice = VoiceEngine()
    private let agent = AgentClient()
    private var serverProcess: Process?

    func start() {
        voice.requestPermission()
        voice.onFinal = { [weak self] text in self?.handle(text) }
        ensureServer()
    }

    /// Auto-start the local Python agent server if it isn't already up, so the
    /// user just launches the app — no terminal step.
    private func ensureServer() {
        Task {
            if await agent.health() { await MainActor.run { self.serverUp = true }; return }
            launchPythonServer()
            // poll until it answers
            for _ in 0..<30 {
                try? await Task.sleep(nanoseconds: 500_000_000)
                if await agent.health() {
                    await MainActor.run { self.serverUp = true }
                    return
                }
            }
        }
    }

    private func launchPythonServer() {
        // Look for the repo root relative to the app, or use CTWIN_REPO env.
        let env = ProcessInfo.processInfo.environment
        let repo = env["CTWIN_REPO"]
            ?? (NSHomeDirectory() + "/Documents/cognitive-twin-agent")
        let p = Process()
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["python3", "-m", "cognitive_twin.voice.server", "--no-open"]
        do { try p.run(); serverProcess = p } catch { /* surfaced via serverUp staying false */ }
    }

    func micTapped() {
        // Siri-style single control:
        //  - if it's talking, tapping interrupts (stops speech)
        //  - if it's listening, tapping stops + submits
        //  - otherwise, start a fresh turn
        if voice.isSpeaking {
            voice.stopSpeaking()
            phase = .idle
            return
        }
        if voice.isListening {
            voice.stopListening()
        } else {
            voice.stopSpeaking()   // cancel any lingering speech
            answer = ""
            transcript = ""
            voice.startListening()
        }
    }

    private func handle(_ text: String) {
        // A new request cancels whatever it was saying (no pile-ups).
        voice.stopSpeaking()
        transcript = text
        phase = .thinking
        Task {
            do {
                let reply = try await agent.ask(text)
                await MainActor.run {
                    self.answer = reply.answer
                    if let m = reply.model { self.modelName = m }
                    self.phase = .speaking
                    self.voice.speak(reply.answer)
                }
            } catch {
                await MainActor.run {
                    self.answer = "Couldn't reach the agent. Is it running?"
                    self.phase = .idle
                }
            }
        }
    }

    /// Map engine state → UI phase + amplitude for the orb.
    var amplitude: CGFloat {
        if voice.isListening { return max(0.25, voice.level) }
        if voice.isSpeaking { return 0.55 }
        if phase == .thinking { return 0.12 }
        return 0.0
    }

    var tint: Color {
        if voice.isListening { return Color(red: 0.04, green: 0.52, blue: 1.0) }   // blue
        if voice.isSpeaking { return Color(red: 0.18, green: 0.80, blue: 0.55) }   // teal/green
        if phase == .thinking { return Color(red: 0.45, green: 0.40, blue: 0.95) } // indigo
        return Color(red: 0.30, green: 0.45, blue: 0.95)
    }

    func syncPhase() {
        if voice.isListening { phase = .listening }
        else if voice.isSpeaking { phase = .speaking }
        else if phase != .thinking { phase = .idle }
    }
}
