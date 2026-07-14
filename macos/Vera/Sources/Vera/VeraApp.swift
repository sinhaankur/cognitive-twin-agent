import SwiftUI
import AppKit
import Foundation
import ServiceManagement

@main
struct VeraApp: App {
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
    private var brainWindow: NSWindow?
    private var eyeWindow: NSWindow?     // her opt-in eye (small, always visible while on)
    private var statusItem: NSStatusItem?
    private var privacyItem: NSMenuItem?
    private var learnItem: NSMenuItem?
    private var eyeItem: NSMenuItem?     // the See-me switch — checkmark shows state
    private var earItem: NSMenuItem?     // the Hear-the-room switch (opt-in)
    private var photosItem: NSMenuItem?  // the Read-my-Photos switch (opt-in)

    func applicationDidFinishLaunching(_ notification: Notification) {
        // one of her per device: if another copy is already running (e.g. a
        // second install), hand over to it and bow out — two Veras would fight
        // over the mic, the servers, and the orb
        let myID = Bundle.main.bundleIdentifier ?? "com.sinhaankur.anita"
        let twins = NSRunningApplication.runningApplications(withBundleIdentifier: myID)
            .filter { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }
        if !twins.isEmpty {
            twins.first?.activate(options: [])
            NSApp.terminate(nil)
            return
        }
        NSApp.setActivationPolicy(.accessory)   // background app, NO Dock icon
        model.openSettings = { [weak self] in self?.showSettings() }
        model.openVoiceLearn = { [weak self] in self?.showVoiceLearn() }
        model.toggleEye = { [weak self] in self?.toggleEye() }
        makeStatusItem()                         // menu-bar icon (like battery) — shows she's active
        makeOrbWindow()
        makeChatWindow()
        model.start()                            // ready + greets independently
        model.refreshActivity()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { self.syncMenuChecks() }
        photosItem?.state = UserDefaults.standard.bool(forKey: "photosOn") ? .on : .off
        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.model.shutdownSpawnedServer() }
        }
        if UserDefaults.standard.bool(forKey: "photosOn") {
            // still ON from last time → refresh what she knows (new albums since),
            // once the local server has had time to come up
            DispatchQueue.main.asyncAfter(deadline: .now() + 10) {
                PhotosReader.scanAndSend { note in NSLog("photos: \(note)") }
            }
        }
    }

    /// A menu-bar status icon (top-right) so you know Anita is running, with
    /// Settings + actions tucked inside its menu.
    private func makeStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = item.button {
            button.image = NSImage(systemSymbolName: "circle.hexagongrid.fill",
                                   accessibilityDescription: model.assistantName)
            button.image?.isTemplate = true
        }
        let menu = NSMenu()
        menu.addItem(withTitle: model.assistantName, action: nil, keyEquivalent: "")
        menu.addItem(.separator())
        // every item carries its canonical SF Symbol — the menu reads at a
        // glance, the way the system's own menus do
        func symbol(_ name: String) -> NSImage? {
            NSImage(systemSymbolName: name, accessibilityDescription: nil)
        }
        let show = NSMenuItem(title: "Open \(model.assistantName)",
                              action: #selector(menuShowOrb), keyEquivalent: "")
        show.image = symbol("circle.hexagongrid.fill")
        show.target = self; menu.addItem(show)
        let chat = NSMenuItem(title: "Chat…", action: #selector(menuChat), keyEquivalent: "")
        chat.image = symbol("bubble.left.and.bubble.right")
        chat.target = self; menu.addItem(chat)
        menu.addItem(.separator())
        // Privacy controls — front and centre.
        privacyItem = NSMenuItem(title: "Private mode (pause learning)",
                                 action: #selector(menuTogglePrivate), keyEquivalent: "")
        privacyItem?.image = symbol("hand.raised")
        privacyItem?.target = self; menu.addItem(privacyItem!)
        let snooze = NSMenuItem(title: "Snooze 30 min", action: #selector(menuSnooze), keyEquivalent: "")
        snooze.image = symbol("moon.zzz")
        snooze.target = self; menu.addItem(snooze)
        learnItem = NSMenuItem(title: "Learn how I work", action: #selector(menuToggleLearn), keyEquivalent: "")
        learnItem?.image = symbol("graduationcap")
        learnItem?.target = self; menu.addItem(learnItem!)
        menu.addItem(.separator())
        let settings = NSMenuItem(title: "Settings…", action: #selector(menuSettings), keyEquivalent: ",")
        settings.image = symbol("gearshape")
        settings.target = self; menu.addItem(settings)
        let voice = NSMenuItem(title: "Teach her a voice…", action: #selector(menuVoice), keyEquivalent: "")
        voice.image = symbol("waveform")
        voice.target = self; menu.addItem(voice)
        let brain = NSMenuItem(title: "See how she thinks…", action: #selector(menuBrain), keyEquivalent: "b")
        brain.image = symbol("brain.head.profile")
        brain.target = self; menu.addItem(brain)
        eyeItem = NSMenuItem(title: "Let her see me (on/off)", action: #selector(menuEye), keyEquivalent: "")
        eyeItem?.image = symbol("eye")
        eyeItem?.target = self; menu.addItem(eyeItem!)
        earItem = NSMenuItem(title: "Let her hear the room (on/off)",
                             action: #selector(menuEar), keyEquivalent: "")
        earItem?.image = symbol("ear")
        earItem?.target = self; menu.addItem(earItem!)
        photosItem = NSMenuItem(title: "Let her read my Photos (on/off)",
                                action: #selector(menuPhotos), keyEquivalent: "")
        photosItem?.image = symbol("photo.on.rectangle")
        photosItem?.target = self; menu.addItem(photosItem!)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Quit \(model.assistantName)", action: #selector(menuQuit), keyEquivalent: "q")
        quit.image = symbol("power")
        quit.target = self; menu.addItem(quit)
        item.menu = menu
        statusItem = item
    }

    @objc private func menuShowOrb() { orbWindow?.makeKeyAndOrderFront(nil) }
    @objc private func menuChat() { toggleChat() }
    @objc private func menuSettings() { showSettings() }
    @objc private func menuVoice() { showVoiceLearn() }
    @objc private func menuBrain() { showBrain() }
    @objc private func menuEye() { toggleEye() }
    @objc private func menuEar() {
        model.ear.toggle()
        // permission is async — reflect the real state once it settles
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            self.earItem?.state = self.model.ear.on ? .on : .off
        }
    }
    @objc private func menuPhotos() { togglePhotos() }
    @objc private func menuQuit() { NSApp.terminate(nil) }

    /// The Read-my-Photos switch. Strictly opt-in: nothing touches the photo
    /// library until the user flips this ON (macOS asks its own permission on
    /// top). ON scans album titles + dates — metadata only, never pixels —
    /// and rescans on each launch while it stays on. OFF stops all reading.
    private func togglePhotos() {
        let on = !UserDefaults.standard.bool(forKey: "photosOn")
        UserDefaults.standard.set(on, forKey: "photosOn")
        photosItem?.state = on ? .on : .off
        guard on else { return }
        PhotosReader.scanAndSend { note in
            NSLog("photos: \(note)")
        }
    }

    /// The See-me switch. ON opens a small floating preview window (her eye is
    /// never on without a visible preview); OFF — or just closing the window —
    /// stops the camera and posts /api/presence/stop so she forgets at once.
    private func toggleEye() {
        if let w = eyeWindow {                 // ON → OFF
            w.close()                          // willClose handler does the rest
            return
        }
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 288, height: 216),
            styleMask: [.titled, .closable, .fullSizeContentView],
            backing: .buffered, defer: false)
        w.title = "she can see you"
        w.level = .floating
        w.isReleasedWhenClosed = false
        // the window is a dark instrument, chrome included — no white bar over
        // a black canvas
        w.titlebarAppearsTransparent = true
        w.appearance = NSAppearance(named: .darkAqua)
        w.backgroundColor = NSColor(red: 0.02, green: 0.024, blue: 0.04, alpha: 1)
        w.isMovableByWindowBackground = true
        w.contentView = NSHostingView(rootView: EyeView())
        NotificationCenter.default.addObserver(
            forName: NSWindow.willCloseNotification, object: w, queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.eyeWindow = nil
                self.model.eyeOn = false
                self.eyeItem?.state = .off
                self.postPresenceStop()
            }
        }
        w.center(); w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        eyeWindow = w
        model.eyeOn = true
        eyeItem?.state = .on
    }

    /// Belt-and-braces forget: the page's pagehide beacon usually fires first,
    /// but the native side never relies on the page for the privacy contract.
    private func postPresenceStop() {
        guard let url = URL(string: "http://127.0.0.1:7878/api/presence/stop") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        URLSession.shared.dataTask(with: req).resume()
    }

    @objc private func menuTogglePrivate() {
        model.setPrivate(!model.activityPrivate)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { self.syncMenuChecks() }
    }
    @objc private func menuSnooze() {
        model.snooze(30)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { self.syncMenuChecks() }
    }
    @objc private func menuToggleLearn() {
        model.setActivityEnabled(!model.activityEnabled)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { self.syncMenuChecks() }
    }

    /// Reflect privacy/learning state as menu checkmarks + update the status glyph.
    private func syncMenuChecks() {
        privacyItem?.state = model.activityPrivate ? .on : .off
        learnItem?.state = model.activityEnabled ? .on : .off
        // when private, dim/slash the menu-bar icon so you can SEE she's paused
        if let b = statusItem?.button {
            let sym = model.activityPrivate ? "moon.zzz.fill" : "circle.hexagongrid.fill"
            b.image = NSImage(systemSymbolName: sym, accessibilityDescription: model.assistantName)
            b.image?.isTemplate = true
        }
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

    /// Open the Brain — a graph of how the twin thinks and learns.
    private func showBrain() {
        if let w = brainWindow {
            w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true); return
        }
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 780, height: 600),
            styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        w.title = "\(model.assistantName) — The Brain"
        w.isReleasedWhenClosed = false
        w.contentView = NSHostingView(rootView: BrainView().environmentObject(model))
        w.center(); w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        brainWindow = w
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
        // The WINDOW is larger than the orb so the glow/blur fades to fully
        // transparent before the window edge — otherwise the blurred bloom gets
        // clipped to the window bounds and shows as a faint square.
        let orb: CGFloat = 84
        let pad: CGFloat = orb * 1.6        // generous transparent margin for the glow
        let win = orb + pad
        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: win, height: win),
            styleMask: [.borderless], backing: .buffered, defer: false)
        w.isOpaque = false
        w.backgroundColor = .clear
        w.level = .floating                       // stays above other windows
        w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        w.isMovableByWindowBackground = true
        w.hasShadow = false                       // no window shadow (that's a box too)
        w.ignoresMouseEvents = false
        w.contentView = NSHostingView(
            rootView: FloatingOrb(model: model) { [weak self] in self?.toggleChat() })
        // place near the top-right by default
        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            w.setFrameOrigin(NSPoint(x: f.maxX - win - 16, y: f.maxY - win - 16))
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
            model.chatOpened()   // opening the chat clears the "thought waiting" glow
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
    /// The See-me switch (her opt-in eye). Wired by the AppDelegate.
    @Published var eyeOn = false
    var toggleEye: (() -> Void)?

    /// Teach Anita a loved one's voice from their messages. Returns sample count.
    func addVoice(person: String, text: String) async -> Int {
        await agent.addVoice(person: person, text: text)
    }

    /// The user renamed their twin — persist it into the persona so the agent
    /// also refers to itself by the new name. (assistantName already persists to
    /// UserDefaults via its didSet.)
    func renamed() {
        let name = assistantName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        Task { await agent.remember("Your name is \(name).") }
    }

    /// Set a recording as the cloned voice (from a file the user picks). Returns
    /// true when the voice is set up and ready.
    func setVoiceFile(path: String, person: String) async -> Bool {
        let ok = await agent.setVoiceClone(path: path, person: person)
        await MainActor.run { self.clonedVoiceReady = ok }
        return ok
    }
    @Published var availableModels: [String] = []
    @Published var speakReplies = true        // toggle voice talk-back
    @Published var turns: [ChatTurn] = []     // the chat conversation
    @Published var hasThoughtWaiting = false  // she has a reflection to share → orb glows
    @Published var clonedVoiceReady = false   // her actual (cloned) voice is set up
    @Published var activityEnabled = false    // she learns from your device activity
    @Published var activityPrivate = false    // private/snooze mode — not observing

    func refreshActivity() {
        Task {
            let s = await agent.activityStatus()
            await MainActor.run { self.activityEnabled = s.enabled; self.activityPrivate = s.isPrivate }
        }
    }
    func setActivityEnabled(_ on: Bool) {
        Task {
            let s = await agent.activityAction(on ? "enable" : "disable")
            await MainActor.run { self.activityEnabled = s.enabled; self.activityPrivate = s.isPrivate }
        }
    }
    func setPrivate(_ on: Bool) {
        Task {
            let s = await agent.activityAction(on ? "private" : "resume")
            await MainActor.run { self.activityPrivate = s.isPrivate }
        }
    }
    func snooze(_ minutes: Int) {
        Task {
            let s = await agent.activityAction("snooze", minutes: minutes)
            await MainActor.run { self.activityPrivate = s.isPrivate }
        }
    }

    /// Speak a reply in her cloned voice if available, else the built-in voice.
    /// Either way the mic opens muted underneath her (VoiceEngine's barge-in
    /// hunt): speak over her and she stops mid-word, your words already caught.
    func speakReply(_ text: String) {
        phase = .speaking
        if clonedVoiceReady {
            // Cloned voice renders + plays server-side (her real voice); the
            // request returns when playback ends, so the orb settles exactly
            // on time — no more length guessing.
            voice.beginExternalSpeech(text)
            Task {
                let ok = await agent.speak(text)
                await MainActor.run {
                    self.voice.endExternalSpeech()
                    if !ok { self.voice.speak(text) }   // fallback
                    else if self.phase == .speaking { self.phase = .idle }
                }
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
    let ear = EarEngine()          // her opt-in ear on the room (ambient sound)
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
        // the ear tells the voice when the room needs isolation ("if needed")
        ear.onNoise = { [weak self] noisy in self?.voice.isolateVoice = noisy }
        enableLaunchAtLogin()      // so Anita is always there after a reboot
        autoUpdate()               // she keeps herself current — nothing to download
        ensureServer()
        launchVizServer()          // the Mind (Brain view + browser) on :7879
        startWatchdog()            // keep her alive if the brain ever stops
    }

    /// Start the Visualize Engine so the Brain window (and the browser) can
    /// show the Mind. If the port is already served, the child exits on its
    /// own — safe to attempt once per launch.
    private var vizProcess: Process?
    private func launchVizServer() {
        guard vizProcess == nil else { return }
        let env = ProcessInfo.processInfo.environment
        let repo = env["CTWIN_REPO"]
            ?? (NSHomeDirectory() + "/Documents/cognitive-twin-agent")
        let p = Process()
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        let pythons = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                       "/usr/bin/python3"]
        let python = pythons.first { FileManager.default.isExecutableFile(atPath: $0) }
        p.executableURL = URL(fileURLWithPath: python ?? "/usr/bin/env")
        p.arguments = (python != nil ? [] : ["python3"])
            + ["-m", "cognitive_twin", "viz", "--no-open", "--port", "7879"]
        do { try p.run(); vizProcess = p } catch { /* Brain view shows a retry */ }
    }

    /// She updates herself: her brain runs straight from the repo, so a
    /// `git pull` there IS the update (the updater script restarts what
    /// changed, and rebuilds this shell only when macos/ changed). Detached,
    /// fast-forward-only, and it never touches local edits. Opt out with
    /// CTWIN_NO_AUTOUPDATE=1.
    private func autoUpdate() {
        let env = ProcessInfo.processInfo.environment
        guard env["CTWIN_NO_AUTOUPDATE"] == nil else { return }
        let repo = env["CTWIN_REPO"]
            ?? (NSHomeDirectory() + "/Documents/cognitive-twin-agent")
        let script = repo + "/scripts/update-vera.sh"
        guard FileManager.default.isExecutableFile(atPath: script) else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: script)
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        try? p.run()               // best-effort; she runs fine without it
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
            let reply = try await agent.ask("Greet me for the day using your greeting tool. One or two warm sentences.", internal: true)
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
                guard let self else { return }
                if let thought = await self.agent.reflect(), !thought.isEmpty {
                    await MainActor.run { self.hasThoughtWaiting = true }
                }
            }
        }
    }

    /// Called when the user opens the chat — clear the "thought waiting" cue.
    func chatOpened() {
        hasThoughtWaiting = false
    }

    /// Auto-start the local Python agent server if it isn't already up, so the
    /// user just launches the app — no terminal step. One attempt at a time:
    /// the watchdog fires every 5s but the server takes longer to bind, so
    /// without the guard she'd spawn a pile of duplicate brains.
    private var ensuringServer = false
    private func ensureServer() {
        guard !ensuringServer else { return }
        ensuringServer = true
        Task {
            defer { ensuringServer = false }
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
        // a previous attempt still alive but unhealthy? replace it, don't stack
        if let sp = serverProcess, sp.isRunning { sp.terminate() }
        // Look for the repo root relative to the app, or use CTWIN_REPO env.
        let env = ProcessInfo.processInfo.environment
        let repo = env["CTWIN_REPO"]
            ?? (NSHomeDirectory() + "/Documents/cognitive-twin-agent")
        let p = Process()
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        // Prefer a real installed python3: a GUI app's PATH is minimal, so
        // `env python3` resolves to /usr/bin/python3 — Xcode's old 3.9.
        let pythons = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                       "/usr/bin/python3"]
        let python = pythons.first { FileManager.default.isExecutableFile(atPath: $0) }
        p.executableURL = URL(fileURLWithPath: python ?? "/usr/bin/env")
        p.arguments = (python != nil ? [] : ["python3"])
            + ["-m", "cognitive_twin.voice.server", "--no-open"]
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

    /// Quit takes the brain down too: a server we spawned must not outlive the
    /// app (stale code keeps serving, and every update needed a manual kill).
    func shutdownSpawnedServer() {
        if let sp = serverProcess, sp.isRunning { sp.terminate() }
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

        // Twin Council: "/council <question>" asks every twin the same thing and
        // shows each take. Same feature as the CLI's /council, in the app.
        if let q = Self.councilQuestion(text) {
            runCouncil(q)
            return
        }

        phase = .thinking
        Task {
            do {
                let answerText: String
                if usingAppleAI {
                    // Fully on-device via Apple's foundation model — no server.
                    let persona = "You are a concise, helpful local-first personal assistant. Keep answers short and spoken-friendly."
                    do {
                        answerText = try await appleAI.ask(text, persona: persona)
                    } catch {
                        // Apple Intelligence failed even after its session
                        // reset — answer THIS turn via the local agent rather
                        // than dead-ending the chat. Selection stays on Apple;
                        // this is a per-turn safety net.
                        let reply = try await agent.ask(text)
                        answerText = reply.answer
                    }
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
                    // The failure must LAND IN THE CHAT — without a bubble the
                    // typed message just vanishes and the whole panel reads as
                    // broken (the original bug: errors only set `answer`).
                    let msg = "I couldn't answer that — my local brain isn't reachable. Give me a few seconds and try again."
                    self.answer = msg
                    self.turns.append(ChatTurn(text: msg, isUser: false))
                    self.phase = .idle
                    self.ensureServer() // kick the watchdog now, not in 5s
                }
            }
        }
    }

    /// Parse a "/council <question>" command. Returns the question, or nil if the
    /// text isn't a council command. Accepts "/council", "council:" as a prefix.
    static func councilQuestion(_ text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespaces)
        for prefix in ["/council", "council:"] {
            if t.lowercased().hasPrefix(prefix) {
                let q = t.dropFirst(prefix.count).trimmingCharacters(in: .whitespaces)
                return q.isEmpty ? nil : q
            }
        }
        return nil
    }

    /// Ask every twin the same question and drop each take into the chat as its
    /// own bubble ("Anita » …"). Reuses the existing turn UI — no new view. One
    /// twin failing shows inline; the rest still answer. Nothing is spoken (a
    /// chorus of voices would be chaos) — this is a read-and-decide moment.
    private func runCouncil(_ question: String) {
        phase = .thinking
        Task {
            let takes = await agent.council(question)
            await MainActor.run {
                self.phase = .idle
                if takes.isEmpty {
                    self.turns.append(ChatTurn(
                        text: "I couldn't convene the council — you may have only one twin, or the brain isn't reachable.",
                        isUser: false))
                    return
                }
                for take in takes {
                    let body = take.error.map { "[couldn't answer: \($0)]" } ?? take.answer
                    self.turns.append(ChatTurn(text: "\(take.name) » \(body)", isUser: false))
                }
                let answered = takes.filter { $0.error == nil }.count
                if answered > 1 {
                    self.turns.append(ChatTurn(
                        text: "— \(answered) voices weighed in. The choice is yours.",
                        isUser: false))
                }
            }
        }
    }

    /// Map engine state → UI phase + amplitude for the orb.
    var amplitude: CGFloat {
        if voice.isListening { return max(0.25, voice.level) }
        // speaking: each word bumps speakPulse (the synthesizer's per-word
        // callback), so her mouth visibly moves; cloned playback holds steady
        if voice.isSpeaking { return 0.40 + voice.speakPulse * 0.45 }
        if phase == .thinking { return 0.12 }
        return 0.0
    }

    /// Spectral sparkle for the orb's core: your sibilants while listening,
    /// her word onsets while speaking.
    var brightness: CGFloat {
        if voice.isListening { return voice.brightness }
        if voice.isSpeaking { return voice.speakPulse * 0.7 }
        return 0
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
