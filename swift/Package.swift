// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "fm-agent",
    platforms: [.macOS("26.0")],
    targets: [
        .executableTarget(name: "fm-agent", path: "Sources/fm-agent")
    ]
)
