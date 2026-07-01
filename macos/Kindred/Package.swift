// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Kindred",
    platforms: [
        .macOS(.v13)   // Speech on-device dictation + modern SwiftUI
    ],
    targets: [
        .executableTarget(
            name: "Kindred",
            path: "Sources/Kindred"
        )
    ]
)
