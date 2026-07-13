import SwiftUI
import WebKit

/// The Mind — the whole app as a living galaxy.
///
/// This view is a window onto the SAME visualization the browser gets: the
/// local Visualize Engine (127.0.0.1:7879), whose Mind page renders the twin's
/// real state — memories as stars in typed spiral arms, faculties as planets
/// riding orbit trails, and a comet that flies an actual thought-path (recall →
/// faculties → the model the policy really routes to). One visualization,
/// everywhere; nothing leaves the machine.
///
/// The page's visual language is adapted from the author's Universe Engine
/// (sinhaankur.com), rebuilt dependency-free in the agent (`cognitive_twin/viz.py`).
struct BrainView: View {
    @State private var serverUp = false
    @State private var checking = true

    private let mindURL = URL(string: "http://127.0.0.1:7879/")!

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
        web.load(URLRequest(url: url))
        return web
    }

    func updateNSView(_ web: WKWebView, context: Context) {
        if web.url == nil { web.load(URLRequest(url: url)) }
    }
}
