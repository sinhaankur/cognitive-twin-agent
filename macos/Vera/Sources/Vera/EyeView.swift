import SwiftUI
import WebKit

/// Her eye — hosts the local /eye page (the owner's optical-flow engine,
/// Shi-Tomasi + Lucas-Kanade running entirely in the page) inside the small
/// always-visible preview window. The webview grants media capture ONLY to
/// 127.0.0.1 and ONLY for the camera — same opt-in, on-device contract as
/// the browser version. macOS still asks the user once (TCC), as it should.
struct EyeView: NSViewRepresentable {
    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let web = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
        web.uiDelegate = context.coordinator
        web.setValue(false, forKey: "drawsBackground")
        if let url = URL(string: "http://127.0.0.1:7878/eye") {
            web.load(URLRequest(url: url))
        }
        return web
    }

    func updateNSView(_ view: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKUIDelegate {
        func webView(_ webView: WKWebView,
                     requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo,
                     type: WKMediaCaptureType,
                     decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(origin.host == "127.0.0.1" && type == .camera ? .grant : .deny)
        }
    }
}
