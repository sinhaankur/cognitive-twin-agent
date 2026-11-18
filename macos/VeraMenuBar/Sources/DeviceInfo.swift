// DeviceInfo — this Mac's identity for the menu's "This Device: name (100.x)"
// line, mimicking Tailscale. Reads the tailnet IP + login from the Tailscale CLI
// when present; falls back to the plain hostname otherwise. Pure read, cached.

import Foundation

enum DeviceInfo {
    /// e.g. "ankursinhas-macbook-pro-1"
    static let hostname: String = {
        ProcessInfo.processInfo.hostName.components(separatedBy: ".").first
            ?? ProcessInfo.processInfo.hostName
    }()

    /// The tailnet IPv4 (100.x), or nil if Tailscale isn't present.
    static let tailnetIP: String? = runTailscale(["ip", "-4"])?
        .split(separator: "\n").first.map(String.init)

    /// The tailnet login (you@tailnet), or the OS user as a fallback.
    static let account: String = {
        if let out = runTailscale(["status", "--self", "--peers=false"]) {
            let cols = out.split(separator: "\n").first?.split(separator: " ",
                omittingEmptySubsequences: true).map(String.init) ?? []
            if cols.count >= 3, cols[2].contains("@") {
                return cols[2].hasSuffix("@") ? String(cols[2].dropLast()) : cols[2]
            }
        }
        return NSUserName()
    }()

    /// "This Device: name (100.x)" — exactly Tailscale's line.
    static var thisDeviceLine: String {
        "This Device: \(hostname)" + (tailnetIP.map { " (\($0))" } ?? "")
    }

    private static func runTailscale(_ args: [String]) -> String? {
        let candidates = [
            "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
            "/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale",
        ]
        guard let bin = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) else {
            return nil
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: bin)
        proc.arguments = args
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()
        do {
            try proc.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            proc.waitUntilExit()
            let s = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return (s?.isEmpty == false) ? s : nil
        } catch { return nil }
    }
}
