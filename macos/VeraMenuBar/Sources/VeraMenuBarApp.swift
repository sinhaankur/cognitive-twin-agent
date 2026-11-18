// VeraMenuBarApp — Vera's native macOS menu-bar app, built to LITERALLY mimic
// Tailscale's menu (Ankur: "literally mimic this · of this standard · native as
// hell · the more native the faster and less to worry about").
//
// It's a SwiftUI MenuBarExtra (the modern NSStatusItem) — launches instantly,
// costs almost nothing idle, and works even when the Python brain is down (it
// shows "offline"). It talks to the brain only over the local /api/privacy.
//
// Layout mapped 1:1 from the real Tailscale menu:
//   Vera                         [Connect toggle]   ← header + big switch
//   Connected / Private                             ← status under the name
//   ──────────────────────────────────────────────
//   ● you@tailnet · Companion + Coding            › ← identity row
//   ──────────────────────────────────────────────
//   This Device: name (100.x.y.z)                   ← device line
//   My Devices                                    › ← (Network Devices ›)
//   Controls · Reach / Safe Mode / Kill Switch    › ← (Exit Nodes ›)
//   ──────────────────────────────────────────────
//   Settings…                                   ⌘,
//   Open Vera
//   Quit                                        ⌘Q

import SwiftUI
import AppKit

@main
struct VeraMenuBarApp: App {
    @StateObject private var client = PrivacyClient()

    var body: some Scene {
        MenuBarExtra {
            MenuContent(client: client)
        } label: {
            // The menu-bar glyph signals the whole posture at a glance, like
            // Tailscale's icon fills when connected.
            Image(systemName: menuGlyph)
        }
        .menuBarExtraStyle(.window)   // a real panel, so we control the layout fully
    }

    private var menuGlyph: String {
        if client.state.locked { return "xmark.octagon.fill" }         // 🚫 lockdown
        if client.state.connected { return "dot.radiowaves.left.and.right" } // connected
        return "mic.fill"                                              // private
    }
}

// MARK: - the menu panel (Tailscale layout)

struct MenuContent: View {
    @ObservedObject var client: PrivacyClient

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().padding(.vertical, 6)
            identityRow
            Divider().padding(.vertical, 6)
            deviceBlock
            Divider().padding(.vertical, 6)
            footer
        }
        .padding(12)
        .frame(width: 300)
        .background(BrandColor.panel)
        .onAppear { client.start() }
        .onDisappear { client.stop() }
    }

    // ── header: "Vera" + the big Connect toggle + status line ──────────────────
    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text("Vera").font(.system(size: 15, weight: .semibold))
                Spacer()
                Toggle("", isOn: Binding(
                    get: { client.state.connected },
                    set: { _ in Task { await client.toggleConnect() } }
                ))
                .toggleStyle(.switch)
                .tint(BrandColor.accent)
                .labelsHidden()
                .disabled(!client.online || client.state.locked)
            }
            Text(statusText)
                .font(.system(size: 11))
                .foregroundStyle(statusColor)
        }
    }

    private var statusText: String {
        if !client.online { return "Offline — Vera isn’t running" }
        if client.state.locked { return "Locked down · think only" }
        return client.state.connected
            ? "Connected · your devices can reach Vera"
            : "Private · this Mac only"
    }

    private var statusColor: Color {
        if !client.online { return BrandColor.muted }
        if client.state.locked { return BrandColor.danger }
        return client.state.connected ? BrandColor.accent : BrandColor.muted
    }

    // ── identity row (Tailscale's avatar · you@github ›) ───────────────────────
    private var identityRow: some View {
        HStack(spacing: 8) {
            Circle().fill(BrandColor.accent).frame(width: 22, height: 22)
                .overlay(Text("V").font(.system(size: 11, weight: .bold))
                    .foregroundStyle(BrandColor.panel))
            VStack(alignment: .leading, spacing: 1) {
                Text(DeviceInfo.account).font(.system(size: 12, weight: .medium))
                Text("Companion + Coding").font(.system(size: 10))
                    .foregroundStyle(BrandColor.muted)
            }
            Spacer()
            Button { openSettings() } label: { Image(systemName: "chevron.right") }
                .buttonStyle(.plain).foregroundStyle(BrandColor.muted)
        }
    }

    // ── device + submenus (Tailscale's This Device / Network Devices / Exit) ───
    private var deviceBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(DeviceInfo.thisDeviceLine)
                .font(.system(size: 11)).foregroundStyle(BrandColor.ink)

            // Reach — the explicit radio, in case you don't use the big toggle
            MenuRow(icon: "lock.fill", title: "Private (this Mac only)",
                    checked: client.state.reach == "private") {
                Task { await client.setReach("private") }
            }
            MenuRow(icon: "iphone", title: "My devices (tailnet)",
                    checked: client.state.reach == "my_devices") {
                Task { await client.setReach("my_devices") }
            }

            // Safe Mode — asks before acting
            MenuRow(icon: "hand.raised.fill", title: "Safe Mode — ask before acting",
                    checked: client.state.safeMode) {
                Task { await client.setSafeMode(!client.state.safeMode) }
            }

            // Kill Switch — danger
            MenuRow(icon: "xmark.octagon.fill", title: "Kill Switch (lockdown)",
                    checked: client.state.locked, danger: true) {
                Task { await client.setLockdown(!client.state.locked) }
            }
        }
    }

    // ── footer (Settings ⌘, / Open Vera / Quit ⌘Q) ─────────────────────────────
    private var footer: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { openSettings() } label: {
                HStack { Text("Settings…"); Spacer(); Text("⌘,").foregroundStyle(BrandColor.muted) }
            }.buttonStyle(.plain)
            Button { open("/?listen=1") } label: { Text("Open Vera") }.buttonStyle(.plain)
            Button { NSApp.terminate(nil) } label: {
                HStack { Text("Quit"); Spacer(); Text("⌘Q").foregroundStyle(BrandColor.muted) }
            }.buttonStyle(.plain).keyboardShortcut("q")
        }
        .font(.system(size: 12))
    }

    private func openSettings() { open("/settings") }
    private func open(_ path: String) {
        if let url = URL(string: "http://127.0.0.1:7878\(path)") { NSWorkspace.shared.open(url) }
    }
}

// A single tappable row with an optional check, matching the native menu feel.
struct MenuRow: View {
    let icon: String
    let title: String
    var checked: Bool = false
    var danger: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .frame(width: 16)
                    .foregroundStyle(danger ? BrandColor.danger : BrandColor.accent)
                Text(title).font(.system(size: 12)).foregroundStyle(BrandColor.ink)
                Spacer()
                if checked {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(danger ? BrandColor.danger : BrandColor.accent)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// Brand colors, macOS-native (the shared VeraTokens is UIKit-guarded; this is the
// AppKit twin, same amber-on-near-black identity from docs/CONTROL-SURFACE-BRAND.md).
enum BrandColor {
    static let accent = Color(red: 0.784, green: 0.600, blue: 0.180)  // #c8992e
    static let danger = Color(red: 0.753, green: 0.282, blue: 0.290)  // #c0484a
    static let panel  = Color(nsColor: .windowBackgroundColor)
    static let ink    = Color(nsColor: .labelColor)
    static let muted  = Color(nsColor: .secondaryLabelColor)
}
