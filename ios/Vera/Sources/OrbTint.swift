import SwiftUI

/// OrbTint — Vera's living colour. Her orb isn't one fixed hue: it drifts gently
/// through her warm amber family with the TIME OF DAY (dawn → day → dusk → night),
/// leans with the STATE she's in (thinking / speaking), and carries a faint
/// weekly rhythm — so she feels like a presence that's *in* the day with you,
/// never a static UI colour. All shifts stay within the warm family (tokens accent
/// #d6a95f); never a hue jump, never neon.
///
/// Used by both the iOS and macOS orbs so she looks like one person everywhere.
enum OrbTint {

    /// The four parts of the day, each a small warm shift of her gold.
    /// Dawn = soft rose-gold, Day = clear gold, Dusk = amber-honey, Night = deep ember.
    private static func timeOfDayColor(_ hour: Int) -> (r: Double, g: Double, b: Double) {
        switch hour {
        case 5..<9:   return (0.86, 0.66, 0.46)   // dawn — rose-gold, waking
        case 9..<17:  return (0.839, 0.663, 0.373) // day — her clear gold (the accent)
        case 17..<21: return (0.92, 0.70, 0.36)   // dusk — amber-honey, golden hour
        default:      return (0.74, 0.56, 0.40)   // night — deep ember, quiet
        }
    }

    /// A tiny weekly lilt so no two days read identically — a few % warmth swing
    /// across the week (Mon a touch cooler/steadier, weekend a touch warmer). Subtle
    /// on purpose: you feel it over days, you don't "see" it in a frame.
    private static func dayWarmth(_ weekday: Int) -> Double {
        // weekday: 1=Sun … 7=Sat (Calendar). Map to −0.02 … +0.03 red lift.
        switch weekday {
        case 1, 7: return 0.03   // weekend — warmer
        case 2:    return -0.02  // Monday — steadier
        default:   return 0.0
        }
    }

    /// Her base ambient colour right now (time of day + the weekly lilt). This is
    /// what "idle" rests on — it quietly differs morning vs night, weekday vs weekend.
    static func ambient(now: Date = Date()) -> Color {
        let cal = Calendar.current
        let hour = cal.component(.hour, from: now)
        let weekday = cal.component(.weekday, from: now)
        var (r, g, b) = timeOfDayColor(hour)
        let lift = dayWarmth(weekday)
        r = min(1, r + lift)
        g = min(1, g + lift * 0.5)
        return Color(red: r, green: g, blue: b)
    }

    /// The orb colour for a given state, blended over the ambient base. State leans
    /// the colour (thinking cools to rose-amber, speaking/active brightens to honey),
    /// but the TIME-OF-DAY ambient still shows through, so she's expressive AND
    /// clearly "in the day". `mood` (−1 heavy … +1 light), when known, nudges warmth.
    static func forState(thinking: Bool, speaking: Bool = false,
                         mood: Double = 0, now: Date = Date()) -> Color {
        var (r, g, b) = components(ambient(now: now))
        if thinking {                 // reflecting — cool toward rose-amber
            r = r * 0.95 + 0.788 * 0.05
            g = g * 0.9  + 0.561 * 0.1
            b = b * 0.85 + 0.420 * 0.15
        } else if speaking {          // alive — brighten toward honey
            r = min(1, r * 0.85 + 0.941 * 0.15)
            g = min(1, g * 0.85 + 0.753 * 0.15)
            b = min(1, b * 0.9  + 0.404 * 0.1)
        }
        // mood: a light moment warms + brightens slightly; a heavy one steadies.
        let m = max(-1, min(1, mood))
        if m > 0 { r = min(1, r + m * 0.04); g = min(1, g + m * 0.03) }
        else if m < 0 { r += m * 0.03; b -= m * 0.02 }  // (m<0 → slightly deeper/cooler)
        return Color(red: r, green: g, blue: b)
    }

    private static func components(_ c: Color) -> (Double, Double, Double) {
        #if canImport(UIKit)
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        UIColor(c).getRed(&r, green: &g, blue: &b, alpha: &a)
        return (Double(r), Double(g), Double(b))
        #else
        return (0.839, 0.663, 0.373)
        #endif
    }
}
