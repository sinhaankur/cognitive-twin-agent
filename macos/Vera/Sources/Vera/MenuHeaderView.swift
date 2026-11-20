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

    // Her presence colour, Tailscale-style: the accent when she's up + present,
    // muted when private, warn while still waking. Used for BOTH the dot and the
    // status word, so the one line reads its state at a glance (Tailscale's green
    // "Connected" is the model — the status colour IS the status).
    private var statusColor: Color {
        if !model.serverUp { return VeraTokens.warn }     // still waking her mind
        if model.activityPrivate { return VeraTokens.muted }  // private, at rest
        return VeraTokens.accent                           // here with you
    }

    // One honest status WORD — crisp, present-tense, never a frozen blank. Mirrors
    // Tailscale's single "Connected" line.
    private var statusText: String {
        if !model.serverUp { return "waking…" }
        if model.activityPrivate { return "private — this Mac only" }
        return model.statusLine.isEmpty ? "here with you" : model.statusLine
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
                        Circle().fill(statusColor).frame(width: 6, height: 6)
                        Text(statusText)
                            .font(.system(size: 11))
                            .foregroundStyle(statusColor)   // the status colour IS the status
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
