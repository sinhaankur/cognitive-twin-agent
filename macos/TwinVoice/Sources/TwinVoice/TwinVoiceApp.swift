import SwiftUI
import AppKit
import Foundation
import ServiceManagement

@main
struct TwinVoiceApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    var body: some Scene { Settings { EmptyView() } }
}

/// The app is exactly two things:
///   1. a small CIRCULAR orb that floats, always on screen, on top of everything;
///   2. a CHAT panel that appears when you click the orb (like Siri today).
/// No Dock icon, no normal window — it runs independently in the background.
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let model = AppModel()
    private var orbWindow: NSWindow!     // the always-on-screen circle
    private var chatWindow: NSWindow!    // the chat panel (toggled)

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)   // background app, NO Dock icon
        makeOrbWindow()
        makeChatWindow()
        model.start()                            // ready + greets independently
    }

    // 1) The floating orb — a small, borderless, always-on-top circle you can
    //    drag anywhere. Clicking it toggles the chat panel.
    private func makeOrbWindow() {
        let size: CGFloat = 84
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: size, height: size),
            styleMask: [.borderless], backing: .buffered, defer: false)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.level = .floating                       // stays above other windows
        w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        w.isMovableByWindowBackground = true
        w.hasShadow = false
        w.ignoresMouseEvents = false
        w.contentView = NSHostingView(
            rootView: FloatingOrb(model: model) { [weak self] in self?.toggleChat() })
        // place near the top-right by default
        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            w.setFrameOrigin(NSPoint(x: f.maxX - size - 24, y: f.maxY - size - 24))
        }
        w.makeKeyAndOrderFront(nil)
        orbWindow = w
    }

    // 2) The chat panel — appears next to the orb on click.
    private func makeChatWindow() {
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 380, height: 520),
            styleMask: [.borderless], backing: .buffered, defer: false)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.level = .floating
        w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        w.isMovableByWindowBackground = true
        w.hasShadow = true
        w.contentView = NSHostingView(
            rootView: ChatPanel(model: model)
                .frame(width: 380, height: 520)
                .background(VisualEffectBackground())
                .clipShape(RoundedRectangle(cornerRadius: 22)))
        chatWindow = w
    }

    private func toggleChat() {
        guard let chat = chatWindow, let orb = orbWindow else { return }
        if chat.isVisible {
            chat.orderOut(nil)
        } else {
            // position the panel just below-left of the orb
            let o = orb.frame
            let x = min(o.maxX - 380, (NSScreen.main?.visibleFrame.maxX ?? o.maxX) - 396)
            let y = o.minY - 528
            chat.setFrameOrigin(NSPoint(x: max(16, x), y: max(16, y)))
            chat.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}

/// One line in the chat panel.
struct ChatTurn: Identifiable {
    let id = UUID()
    let text: String
    let isUser: Bool
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
    @Published var showSettings = false
    @Published var availableModels: [String] = []
    @Published var speakReplies = true        // toggle voice talk-back
    @Published var turns: [ChatTurn] = []     // the chat conversation
    // The twin's name — the user's to choose. Defaults to Anita.
    @Published var assistantName: String =
        UserDefaults.standard.string(forKey: "assistantName") ?? "Anita" {
        didSet { UserDefaults.standard.set(assistantName, forKey: "assistantName") }
    }
    // Orb size — adapts to screen, user-adjustable (persisted).
    @Published var orbSize: CGFloat = AppModel.defaultOrbSize() {
        didSet { UserDefaults.standard.set(Double(orbSize), forKey: "orbSize") }
    }

    /// Default orb size scaled to the main screen resolution (smaller on small
    /// displays, larger on big ones), unless the user has set their own.
    static func defaultOrbSize() -> CGFloat {
        if let saved = UserDefaults.standard.object(forKey: "orbSize") as? Double, saved > 0 {
            return CGFloat(saved)
        }
        let h = NSScreen.main?.frame.height ?? 1080
        // ~6% of screen height, clamped to a sensible range.
        return min(120, max(56, h * 0.06))
    }

    let voice = VoiceEngine()
    private let agent = AgentClient()
    private let appleAI = AppleIntelligence()
    private var serverProcess: Process?

    // Special model id for the on-device Apple model.
    static let appleModelID = "Apple Intelligence (on-device)"
    var usingAppleAI: Bool { modelName == Self.appleModelID }
    var appleAvailable: Bool { AppleIntelligence.isAvailable }
    var appleStatus: String { AppleIntelligence.statusText }

    func start() {
        voice.requestPermission()
        voice.onFinal = { [weak self] text in self?.handle(text) }
        enableLaunchAtLogin()      // so Anita is always there after a reboot
        ensureServer()
        startWatchdog()            // keep her alive if the brain ever stops
    }

    /// Register Anita to launch automatically at login (macOS 13+ SMAppService),
    /// so she's present every time without the user starting her.
    private func enableLaunchAtLogin() {
        if #available(macOS 13.0, *) {
            do {
                if SMAppService.mainApp.status != .enabled {
                    try SMAppService.mainApp.register()
                }
            } catch { /* not fatal — she still runs this session */ }
        }
    }

    /// A gentle watchdog: every few seconds, make sure the brain is reachable;
    /// if it has died, quietly bring it back. Reliability = her presence.
    private var watchdog: Timer?
    private func startWatchdog() {
        watchdog?.invalidate()
        watchdog = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                let up = await self.agent.health()
                self.serverUp = up
                if !up { self.ensureServer() }
            }
        }
    }

    /// Greet the user once on launch (good morning + weather), spoken aloud.
    private var didGreet = false
    private func greetOnLaunch() async {
        guard !didGreet else { return }
        didGreet = true
        do {
            let reply = try await agent.ask("Greet me for the day using your greeting tool. One or two warm sentences.")
            await MainActor.run {
                self.answer = reply.answer
                if let m = reply.model { self.modelName = m }
                if self.speakReplies { self.phase = .speaking; self.voice.speak(reply.answer) }
            }
        } catch { /* greeting is best-effort */ }
    }

    /// Auto-start the local Python agent server if it isn't already up, so the
    /// user just launches the app — no terminal step.
    private func ensureServer() {
        Task {
            if await agent.health() {
                await MainActor.run { self.serverUp = true }
                await greetOnLaunch()
                return
            }
            launchPythonServer()
            // poll until it answers
            for _ in 0..<30 {
                try? await Task.sleep(nanoseconds: 500_000_000)
                if await agent.health() {
                    await MainActor.run { self.serverUp = true }
                    await greetOnLaunch()
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
        // The app is an interactive assistant — give its agent internet (search,
        // weather) by default. The CLI stays local-first unless CTWIN_WEB is set.
        var childEnv = env
        childEnv["CTWIN_WEB"] = "1"
        p.environment = childEnv
        do { try p.run(); serverProcess = p } catch { /* surfaced via serverUp staying false */ }
    }

    /// Submit a typed question (from the input bar).
    func submitText(_ text: String) {
        voice.stopSpeaking()
        handle(text)
    }

    /// Load installed models (for the settings picker). Apple Intelligence is
    /// offered first when it's available on this Mac (most private option).
    func refreshModels() {
        Task {
            var models = await agent.models()
            if AppleIntelligence.isAvailable {
                models.insert(Self.appleModelID, at: 0)
            }
            await MainActor.run { self.availableModels = models }
        }
    }

    /// Switch the active model live. Apple Intelligence is handled in-app; Ollama
    /// models are switched on the server.
    func selectModel(_ name: String) {
        if name == Self.appleModelID {
            appleAI.reset()
            modelName = name
            return
        }
        Task {
            let ok = await agent.setModel(name)
            if ok { await MainActor.run { self.modelName = name } }
        }
    }

    /// Wipe the local conversation memory (privacy control).
    func clearMemory() {
        Task { await agent.clearMemory() }
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
        turns.append(ChatTurn(text: text, isUser: true))
        phase = .thinking
        Task {
            do {
                let answerText: String
                if usingAppleAI {
                    // Fully on-device via Apple's foundation model — no server.
                    let persona = "You are a concise, helpful local-first personal assistant. Keep answers short and spoken-friendly."
                    answerText = try await appleAI.ask(text, persona: persona)
                } else {
                    let reply = try await agent.ask(text)
                    if let m = reply.model { await MainActor.run { self.modelName = m } }
                    answerText = reply.answer
                }
                await MainActor.run {
                    self.answer = answerText
                    self.turns.append(ChatTurn(text: answerText, isUser: false))
                    if self.speakReplies {
                        self.phase = .speaking
                        self.voice.speak(answerText)
                    } else {
                        self.phase = .idle
                    }
                }
            } catch {
                await MainActor.run {
                    self.answer = self.usingAppleAI
                        ? "Apple Intelligence isn't available right now."
                        : "Couldn't reach the agent. Is it running?"
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
