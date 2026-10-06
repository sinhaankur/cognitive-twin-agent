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
            } else {
                VStack(spacing: 10) {
                    if checking {
                        ProgressView("Waking the Mind…")
                    } else {
                        Text("The Mind isn't awake yet.").font(.headline)
                        Text("Its engine starts with the app — give it a few seconds.")
                            .foregroundStyle(.secondary)
                        Button("Try again") {
                            checking = true
                            Task {
                                _ = await probe()
                                checking = false
                            }
                        }
                    }
                }
            }
        }
        .frame(minWidth: 760, minHeight: 560)
        .task {
            // poll until the viz server answers (the app launches it at start)
            for _ in 0..<20 {
                if await probe() { return }
                try? await Task.sleep(nanoseconds: 700_000_000)
            }
            checking = false
        }
    }

    @discardableResult
    private func probe() async -> Bool {
        var req = URLRequest(url: mindURL)
        req.timeoutInterval = 2
        if let (_, resp) = try? await URLSession.shared.data(for: req),
           (resp as? HTTPURLResponse)?.statusCode == 200 {
            serverUp = true
            return true
        }
        return false
    }
}

/// A minimal WKWebView host — local page only (127.0.0.1), nothing else.
private struct MindWebView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let web = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        web.setValue(false, forKey: "drawsBackground")   // let the page's space show
        // a magnified webview crops the canvas and throws the heart off-centre
        // ("unable to zoom and center it") — the page owns zoom, not the view
        web.allowsMagnification = false
        web.load(URLRequest(url: url))
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        if web.magnification != 1 { web.magnification = 1 }
        if web.url == nil { web.load(URLRequest(url: url)) }
    }
}
