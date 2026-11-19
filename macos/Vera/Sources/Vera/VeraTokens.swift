// GENERATED from cognitive_twin/design/tokens.json by build_tokens.py — do not edit by hand.
// The iOS app's half of Vera's one shared design system (Tailscale-quality).
import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

enum VeraTokens {
    /// A Color that resolves light/dark from the system appearance — on BOTH
    /// platforms. (It used to return `light` unconditionally on macOS, so every
    /// token stayed on its light-mode value even inside a dark panel — which is
    /// why the greens read harsh/wrong on the dark chat surface.)
    static func dynamic(light: Color, dark: Color) -> Color {
        #if canImport(UIKit)
        return Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
        #elseif canImport(AppKit)
        return Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return NSColor(isDark ? dark : light)
        })
        #else
        return light
        #endif
    }

    // Accent — the NATIVE system accent. On macOS this is whatever the user
    // picked in System Settings ▸ Appearance ▸ Accent color (blue by default);
    // on iOS it's the app's tint. It already adapts to light/dark automatically,
    // so the app feels like it belongs to the OS — no hand-tuned brand hex, no
    // "off in dark mode" problem. This is the most native possible choice.
    #if canImport(AppKit) && !canImport(UIKit)
    /// accent — the user's system accent color (macOS, auto light/dark).
    static let accent = Color(nsColor: .controlAccentColor)
    /// accentInk — accent for text/emphasis (slightly stronger).
    static let accentInk = Color(nsColor: .controlAccentColor)
    /// accentSoft — a faint wash of the accent for 'on' backgrounds.
    static let accentSoft = Color(nsColor: .controlAccentColor).opacity(0.14)
    #else
    /// accent — the app's tint (iOS, auto light/dark).
    static let accent = Color.accentColor
    static let accentInk = Color.accentColor
    static let accentSoft = Color.accentColor.opacity(0.14)
    #endif
    /// bg — from tokens.json (light/dark).
    static let bg = dynamic(light: Color(red: 0.980, green: 0.980, blue: 0.980), dark: Color(red: 0.078, green: 0.082, blue: 0.094))
    /// panel — from tokens.json (light/dark).
    static let panel = dynamic(light: Color(red: 1.000, green: 1.000, blue: 1.000), dark: Color(red: 0.110, green: 0.114, blue: 0.129))
    /// ink — from tokens.json (light/dark).
    static let ink = dynamic(light: Color(red: 0.086, green: 0.090, blue: 0.102), dark: Color(red: 0.949, green: 0.953, blue: 0.961))
    /// muted — from tokens.json (light/dark).
    static let muted = dynamic(light: Color(red: 0.439, green: 0.443, blue: 0.435), dark: Color(red: 0.604, green: 0.612, blue: 0.631))
    /// line — from tokens.json (light/dark).
    static let line = dynamic(light: Color(red: 0.922, green: 0.922, blue: 0.914), dark: Color(red: 0.165, green: 0.169, blue: 0.188))
    /// warn — from tokens.json (light/dark).
    static let warn = dynamic(light: Color(red: 0.690, green: 0.416, blue: 0.000), dark: Color(red: 0.878, green: 0.643, blue: 0.290))
    /// warnSoft — from tokens.json (light/dark).
    static let warnSoft = dynamic(light: Color(red: 0.992, green: 0.953, blue: 0.890), dark: Color(red: 0.180, green: 0.149, blue: 0.082))
    /// danger — from tokens.json (light/dark).
    static let danger = dynamic(light: Color(red: 0.753, green: 0.224, blue: 0.169), dark: Color(red: 0.878, green: 0.416, blue: 0.369))
    /// dangerSoft — from tokens.json (light/dark).
    static let dangerSoft = dynamic(light: Color(red: 0.984, green: 0.925, blue: 0.922), dark: Color(red: 0.180, green: 0.102, blue: 0.094))
}
