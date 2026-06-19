// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TwinVoice",
    platforms: [
        .macOS(.v13)   // Speech on-device dictation + modern SwiftUI
    ],
    targets: [
        .executableTarget(
            name: "TwinVoice",
            path: "Sources/TwinVoice"
        )
    ]
)
