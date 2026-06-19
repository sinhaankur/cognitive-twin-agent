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
    private var settingsWindow: NSWindow?

    private var voiceLearnWindow: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)   // background app, NO Dock icon
        model.openSettings = { [weak self] in self?.showSettings() }
        model.openVoiceLearn = { [weak self] in self?.showVoiceLearn() }
        makeOrbWindow()
        makeChatWindow()
        model.start()                            // ready + greets independently
    }

    private func showVoiceLearn() {
        if let w = voiceLearnWindow {
            w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return
        }
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 480, height: 480),
            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        w.title = "Teach \(model.assistantName) a voice"
        w.isReleasedWhenClosed = false
        w.contentView = NSHostingView(rootView: VoiceLearnView().environmentObject(model))
        w.center(); w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        voiceLearnWindow = w
    }

    /// Open Settings as a real window (reliable from the borderless panel).
    private func showSettings() {
        if let w = settingsWindow {
            w.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 440, height: 520),
            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        w.title = "\(model.assistantName) — Settings"
        w.isReleasedWhenClosed = false
        w.contentView = NSHostingView(rootView: SettingsView().environmentObject(model))
        w.center()
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        settingsWindow = w
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
    /// Wired by the AppDelegate to open settings as a real window (a .sheet won't
    /// reliably present from the borderless floating panel).
    var openSettings: (() -> Void)?
    /// Opens the gentle "teach a loved one's voice" window.
    var openVoiceLearn: (() -> Void)?

    /// Teach Anita a loved one's voice from their messages. Returns sample count.
    func addVoice(person: String, text: String) async -> Int {
        await agent.addVoice(person: person, text: text)
    }
    @Published var availableModels: [String] = []
    @Published var speakReplies = true        // toggle voice talk-back
    @Published var turns: [ChatTurn] = []     // the chat conversation
    @Published var hasThoughtWaiting = false  // she has a reflection to share → orb glows
    @Published var clonedVoiceReady = false   // her actual (cloned) voice is set up

    /// Speak a reply in her cloned voice if available, else the built-in voice.
    /// The orb shows the speaking state for the rough duration either way.
    func speakReply(_ text: String) {
        phase = .speaking
        if clonedVoiceReady {
            // Cloned voice renders + plays server-side (her real voice).
            Task {
                let ok = await agent.speak(text)
                if !ok { await MainActor.run { self.voice.speak(text) } }  // fallback
                // settle the orb after a rough estimate of speech length
                let secs = min(20.0, 1.0 + Double(text.count) * 0.06)
                try? await Task.sleep(nanoseconds: UInt64(secs * 1_000_000_000))
                await MainActor.run { if self.phase == .speaking { self.phase = .idle } }
            }
        } else {
            voice.speak(text)
        }
    }
    // The twin's name — the user's to choose. Defaults to Anita.
    @Published var assistantName: String =
        UserDefaults.standard.string(forKey: "assistantName") ?? "Anita Sinha" {
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

    /// Greet the user once on launch (good morning + weather), spoken aloud, then
    /// share any thoughts she had about their projects while they were away.
    private var didGreet = false
    private func greetOnLaunch() async {
        guard !didGreet else { return }
        didGreet = true
        do {
            let reply = try await agent.ask("Greet me for the day using your greeting tool. One or two warm sentences.")
            await MainActor.run {
                self.answer = reply.answer
                if let m = reply.model { self.modelName = m }
                self.turns.append(ChatTurn(text: reply.answer, isUser: false))
                if self.speakReplies { self.speakReply(reply.answer) }
            }
        } catch { /* greeting is best-effort */ }
        // Is her actual (cloned) voice ready? If so, she speaks in it from now on.
        let ready = await agent.cloneReady()
        await MainActor.run { self.clonedVoiceReady = ready }
        await shareReflections()
        startReflecting()
    }

    /// If she's been thinking about your projects, surface those thoughts.
    private func shareReflections() async {
        let thoughts = await agent.reflections()
        guard !thoughts.isEmpty else { return }
        await MainActor.run {
            for t in thoughts.prefix(2) {
                self.turns.append(ChatTurn(text: "💭 \(t)", isUser: false))
            }
        }
    }

    /// While she's running, let her quietly think about your projects now and
    /// then (every ~20 min). When a new thought lands, the orb gently signals it.
    private var reflectTimer: Timer?
    private func startReflecting() {
        reflectTimer?.invalidate()
        reflectTimer = Timer.scheduledTimer(withTimeInterval: 1200, repeats: true) { [weak self] _ in
            Task {
                if let thought = await self?.agent.reflect(), !thought.isEmpty {
                    await MainActor.run { self?.hasThoughtWaiting = true }
                }
            }
        }
    }

    /// Called when the user opens the chat — clear the "thought waiting" cue.
    func chatOpened() {
        hasThoughtWaiting = false
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
            ensureOllama()        // her brain's brain — start it if it's down
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

    /// Make sure Ollama (the local model runtime) is running. Reliability: Anita
    /// shouldn't go brain-dead just because Ollama stopped. Best-effort, quiet.
    private var ollamaProcess: Process?
    private func ensureOllama() {
        // already running? leave it.
        let probe = Process()
        probe.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        probe.arguments = ["-x", "ollama"]
        try? probe.run(); probe.waitUntilExit()
        if probe.terminationStatus == 0 { return }

        // try `ollama serve` from common install locations
        for path in ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama"] {
            if FileManager.default.fileExists(atPath: path) {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: path)
                p.arguments = ["serve"]
                do { try p.run(); ollamaProcess = p; return } catch {}
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
        childEnv["COQUI_TOS_AGREED"] = "1"   // XTTS license: agreed (so her voice works headless)
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
                        self.speakReply(answerText)
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
