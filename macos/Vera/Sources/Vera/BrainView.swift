import SwiftUI
import WebKit

/// The Mind — one calm, legible, animated thinking pipeline.
///
/// This replaces the old noisy galaxy. It's a window onto the app server's
/// `/mind` page (127.0.0.1:7878/mind): you ask her something and WATCH the
/// thought move through her, step by step — your question → the memories &
/// documents she actually retrieves (RAG, with sources + match %) → how she
/// feels (mood + a readable stress bar) → her grounded answer. Every mark
/// means something; the steps light up in sequence and then rest (calm, not a
/// forever-churning starfield). Adapts to dark/light. Nothing leaves the
/// machine. Data comes from the honest `/api/thought` endpoint — no invented
/// steps. (The old galaxy engine at :7879 remains for the deep "details" view.)
struct BrainView: View {
    @State private var serverUp = false
    @State private var checking = true

    // the legible pipeline page, served by the app server (:7878)
    private let mindURL = URL(string: "http://127.0.0.1:7878/mind")!

    var body: some View {
        ZStack {
            if serverUp {
                MindWebView(url: mindURL)
                    .ignoresSafeArea()
                    .id("mind")          // stable identity — never recreated on re-render
            } else {
                // Obsidian-dark waking panel (matches the in-page overlay) so the
                // app never flashes a bare/mismatched loading state.
                ZStack {
                    Color(red: 0.102, green: 0.102, blue: 0.102).ignoresSafeArea()
                    VStack(spacing: 14) {
                        if checking {
                            ProgressView()
                                .progressViewStyle(.circular)
                                .tint(Color(red: 0.66, green: 0.33, blue: 0.97))   // Obsidian purple
                            Text("Waking the Mind")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.9))
                            Text("Her brain runs on this device — loading her model takes a moment.")
                                .font(.system(size: 13))
                                .foregroundStyle(.white.opacity(0.5))
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: 320)
                        } else {
                            Text("The Mind isn't awake yet.")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.9))
                            Text("Its engine starts with the app — give it a few seconds.")
                                .font(.system(size: 13))
                                .foregroundStyle(.white.opacity(0.5))
                                .multilineTextAlignment(.center)
                            Button("Try again") {
                                checking = true
                                Task {
                                    let deadline = Date().addingTimeInterval(120)
                                    while Date() < deadline { if await probe() { break }
                                        try? await Task.sleep(nanoseconds: 1_000_000_000) }
                                    checking = false
                                }
                            }
                            .tint(Color(red: 0.66, green: 0.33, blue: 0.97))
                        }
                    }
                }
            }
        }
        .frame(minWidth: 760, minHeight: 560)
        .task {
            // Poll until the /mind page serves, then hand off to the page itself:
            // the page has its own Obsidian "Waking the Mind" overlay that waits
            // for her brain to be model-ready and retries on its own. So here we
            // only need the static page to load — but her brain's COLD model load
            // can take 30–100s, far past the old ~14s ceiling (that was the
            // "doesn't load" dead-end). Poll patiently for ~2 min; the UI shows a
            // calm spinner the whole time, never a premature failure.
            let deadline = Date().addingTimeInterval(120)
            while Date() < deadline {
                if await probe() { return }
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
            checking = false   // only after a genuinely long wait do we offer Try again
        }
    }

    @discardableResult
    private func probe() async -> Bool {
        var req = URLRequest(url: mindURL)
        req.timeoutInterval = 3
        if let (_, resp) = try? await URLSession.shared.data(for: req),
           (resp as? HTTPURLResponse)?.statusCode == 200 {
            serverUp = true
            return true
        }
        return false
    }
}

/// A minimal WKWebView host — local page only (127.0.0.1), nothing else. The web
/// view is created and loaded ONCE and then left alone: SwiftUI re-renders of the
/// parent used to re-fire updateNSView and reload the page, which read as the Mind
/// "flickering / going off at random". A coordinator tracks that we've loaded, so
/// updateNSView never reloads a page that's already up.
private struct MindWebView: NSViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coordinator { Coordinator() }
    final class Coordinator { var loaded = false }

    func makeNSView(context: Context) -> WKWebView {
        let web = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        web.setValue(false, forKey: "drawsBackground")   // let the page's space show
        web.allowsMagnification = false                  // the page owns zoom, not the view
        web.load(URLRequest(url: url))
        context.coordinator.loaded = true
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        // Load ONCE. Only (re)load if we somehow never loaded AND there's no page —
        // never reload a page that's already there (that was the flicker).
        if !context.coordinator.loaded && web.url == nil {
            web.load(URLRequest(url: url))
            context.coordinator.loaded = true
        }
    }
}
