import SwiftUI
import AppKit

/// The rich header at the top of the menu-bar dropdown — Tailscale-grade.
///
/// Tailscale's menu opens with a bold title, a one-line status, and a primary
/// on/off toggle, then an identity row ("This Device: … 100.x"). Ours mirrors
/// that: her name + the live status line ("here with you" / "thinking…"), a
/// primary **Active ↔ Private** switch, and a "This Mac · <host>" identity row.
/// A plain run of `NSMenuItem`s can't carry a real toggle or two-line identity,
/// so this is a SwiftUI view hosted inside one `NSMenuItem` at the top.
struct MenuHeaderView: View {
    @ObservedObject var model: AppModel
    /// Flip Private mode (pause/resume all observation) — wired to the same path
    /// the old "Private mode" item used, so behaviour is unchanged.
    var onTogglePrivate: () -> Void

    private var deviceName: String {
        Host.current().localizedName ?? "This Mac"
    }

    // Her presence colour: calm gold when present, dimmed when paused/private.
    private var dotColor: Color {
        if model.activityPrivate { return VeraTokens.warn }
        return model.serverUp ? VeraTokens.accent : VeraTokens.warn
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Title + primary toggle, like Tailscale's "Tailscale / Connected" row.
            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(model.assistantName)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.primary)
                    HStack(spacing: 5) {
                        Circle().fill(dotColor).frame(width: 6, height: 6)
                        Text(model.activityPrivate ? "private — not observing"
                                                   : model.statusLine)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 12)
                // The one primary switch — "Active" (learning/observing) vs Private.
                // ON = active & present; OFF = private, paused.
                Toggle("", isOn: Binding(
                    get: { !model.activityPrivate },
                    set: { _ in onTogglePrivate() }))
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .tint(VeraTokens.accent)
                    .help(model.activityPrivate ? "Resume — let her be present again"
                                                : "Private mode — pause all observation")
            }

            Divider().opacity(0.6)

            // Identity row — "This Mac · <host>", echoing Tailscale's device line.
            HStack(spacing: 7) {
                Image(systemName: "laptopcomputer")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                Text("This Mac · \(deviceName)")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .padding(.horizontal, 14)
        .padding(.top, 12)
        .padding(.bottom, 8)
        .frame(width: 260, alignment: .leading)
    }
}
