// GENERATED from cognitive_twin/design/tokens.json by build_tokens.py — do not edit by hand.
// The iOS app's half of Vera's one shared design system (Tailscale-quality).
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

enum VeraTokens {
    /// A Color that resolves light/dark from the system appearance.
    static func dynamic(light: Color, dark: Color) -> Color {
        #if canImport(UIKit)
        return Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
        #else
        return light
        #endif
    }

    /// accent — from tokens.json (light/dark).
    static let accent = dynamic(light: Color(red: 0.063, green: 0.639, blue: 0.498), dark: Color(red: 0.243, green: 0.812, blue: 0.557))
    /// accentInk — from tokens.json (light/dark).
    static let accentInk = dynamic(light: Color(red: 0.039, green: 0.498, blue: 0.388), dark: Color(red: 0.243, green: 0.812, blue: 0.557))
    /// accentSoft — from tokens.json (light/dark).
    static let accentSoft = dynamic(light: Color(red: 0.910, green: 0.969, blue: 0.945), dark: Color(red: 0.086, green: 0.204, blue: 0.165))
    /// bg — from tokens.json (light/dark).
    static let bg = dynamic(light: Color(red: 0.965, green: 0.965, blue: 0.961), dark: Color(red: 0.090, green: 0.090, blue: 0.102))
    /// panel — from tokens.json (light/dark).
    static let panel = dynamic(light: Color(red: 1.000, green: 1.000, blue: 1.000), dark: Color(red: 0.122, green: 0.122, blue: 0.137))
    /// ink — from tokens.json (light/dark).
    static let ink = dynamic(light: Color(red: 0.102, green: 0.102, blue: 0.098), dark: Color(red: 0.929, green: 0.929, blue: 0.929))
    /// muted — from tokens.json (light/dark).
    static let muted = dynamic(light: Color(red: 0.420, green: 0.420, blue: 0.400), dark: Color(red: 0.608, green: 0.608, blue: 0.608))
    /// line — from tokens.json (light/dark).
    static let line = dynamic(light: Color(red: 0.925, green: 0.925, blue: 0.918), dark: Color(red: 0.173, green: 0.173, blue: 0.192))
    /// warn — from tokens.json (light/dark).
    static let warn = dynamic(light: Color(red: 0.690, green: 0.416, blue: 0.000), dark: Color(red: 0.878, green: 0.643, blue: 0.290))
    /// warnSoft — from tokens.json (light/dark).
    static let warnSoft = dynamic(light: Color(red: 0.992, green: 0.953, blue: 0.890), dark: Color(red: 0.180, green: 0.149, blue: 0.082))
    /// danger — from tokens.json (light/dark).
    static let danger = dynamic(light: Color(red: 0.753, green: 0.224, blue: 0.169), dark: Color(red: 0.878, green: 0.416, blue: 0.369))
    /// dangerSoft — from tokens.json (light/dark).
    static let dangerSoft = dynamic(light: Color(red: 0.984, green: 0.925, blue: 0.922), dark: Color(red: 0.180, green: 0.102, blue: 0.094))
}
