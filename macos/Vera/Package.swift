// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Vera",
    platforms: [
        .macOS(.v13)   // Speech on-device dictation + modern SwiftUI
    ],
    targets: [
        .executableTarget(
            name: "Vera",
            path: "Sources/Vera"
        )
    ]
)
