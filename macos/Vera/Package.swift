// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Vera",
    platforms: [
        .macOS(.v13)   // Speech on-device dictation + modern SwiftUI
    ],
    targets: [
        // Tiny ObjC shim: run a closure inside an @try/@catch so a thrown
        // NSException (e.g. the Photos framework's PHQuery predicate aborts)
        // becomes a Swift-catchable error instead of a SIGABRT that kills the
        // whole app. Swift cannot catch ObjC exceptions natively; this bridges it.
        .target(
            name: "ObjCGuard",
            path: "Sources/ObjCGuard"
        ),
        .executableTarget(
            name: "Vera",
            dependencies: ["ObjCGuard"],
            path: "Sources/Vera"
        )
    ]
)
