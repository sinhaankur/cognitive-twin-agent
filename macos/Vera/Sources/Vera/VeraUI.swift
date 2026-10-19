import SwiftUI
import AppKit

// MARK: - Unified window chrome
//
// Every auxiliary window (Settings, Remember, The Brain, Teach a voice,
// Onboarding) is built through ONE helper so they all share the same chrome:
// a hidden-but-present titlebar with a full-size content view, consistent
// corner feel, a remembered size/position across launches, and a sensible
// minimum size. Before this, each window was hand-rolled with slightly
// different styleMask / sizing / no frame memory — the "it's a toy" tell.

extension AppDelegate {
    /// Build a standard Vera window hosting a SwiftUI root view.
    /// - autosave: a stable key so the window remembers its frame between launches.
    /// - resizable: Brain wants it; the forms don't.
    @MainActor
    func makeWindow<Root: View>(
        title: String,
        root: Root,
        model: AppModel,
        size: NSSize,
        minSize: NSSize? = nil,
        resizable: Bool = false,
        autosave: String
    ) -> NSWindow {
        // NSHostingController (not a bare NSHostingView) gives SwiftUI a proper
        // layout context — a grouped Form in a raw hosting view collapses to zero
        // height (the old "Settings opens blank" bug).
        let host = NSHostingController(rootView: AnyView(root.environmentObject(model)))
        let w = NSWindow(contentViewController: host)
        var mask: NSWindow.StyleMask = [.titled, .closable, .miniaturizable, .fullSizeContentView]
        if resizable { mask.insert(.resizable) }
        w.styleMask = mask
        w.title = title
        w.titlebarAppearsTransparent = true          // content runs under the titlebar
        w.titleVisibility = NSWindow.TitleVisibility.hidden  // the view supplies its own header
        w.isMovableByWindowBackground = true
        w.isReleasedWhenClosed = false
        w.setContentSize(size)
        if let m = minSize { w.contentMinSize = m }
        w.setFrameAutosaveName(autosave)              // remember where the user put it
        if w.frame.origin == .zero { w.center() }     // first run only
        return w
    }

    /// Bring a window to the front (shared by every show* method).
    @MainActor
    func present(_ w: NSWindow) {
        w.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }
}

// MARK: - Design-system primitives (SwiftUI)
//
// Shared building blocks so Settings / Remember / Brain read as ONE product:
// a consistent window header, section card, and section heading. All colour +
// spacing comes from VeraTokens (the one source of truth), never ad-hoc hex.

/// The standard header every Vera window opens with: a small live orb, the
/// title, an optional subtitle, and a close button. Gives all the windows one
/// identity instead of a bare system titlebar.
struct VeraWindowHeader: View {
    @EnvironmentObject var model: AppModel
    let title: String
    var subtitle: String? = nil
    var onClose: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 12) {
            LiveOrb(model: model, size: 34)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 17, weight: .semibold))
                if let subtitle {
                    Text(subtitle).font(.system(size: 11.5)).foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let onClose {
                Button(action: onClose) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title3).foregroundStyle(.secondary)
                }.buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 18).padding(.bottom, 14)
    }
}

/// A grouped card — the one container shape for a section of content.
struct SectionCard<Content: View>: View {
    var title: String? = nil
    var footnote: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let title {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .semibold)).tracking(0.8)
                    .foregroundStyle(.secondary)
            }
            content
            if let footnote {
                Text(footnote).font(.system(size: 11)).foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.primary.opacity(0.04)))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(VeraTokens.line, lineWidth: 1))
    }
}

/// A calm empty/placeholder state — one icon, one line, consistent everywhere.
struct VeraEmptyState: View {
    let icon: String
    let title: String
    var message: String? = nil

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 26, weight: .light))
                .foregroundStyle(VeraTokens.accent.opacity(0.8))
            Text(title).font(.system(size: 14, weight: .semibold))
            if let message {
                Text(message).font(.system(size: 12))
                    .foregroundStyle(.secondary).multilineTextAlignment(.center)
                    .frame(maxWidth: 280)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 36)
    }
}
