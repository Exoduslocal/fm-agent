import Foundation

/// The agent may only touch files under the directory it was launched from.
let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    .resolvingSymlinksInPath().standardizedFileURL

struct AgentError: Error, CustomStringConvertible {
    let description: String
    init(_ description: String) { self.description = description }
}

func safePath(_ raw: String) throws -> URL {
    var rel = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    while rel.hasPrefix("./") { rel.removeFirst(2) }
    let url = root.appendingPathComponent(rel).resolvingSymlinksInPath().standardizedFileURL
    guard url.path == root.path || url.path.hasPrefix(root.path + "/") else {
        throw AgentError("path \(raw) is outside the project. Use a relative path like app.py")
    }
    return url
}

/// Cap tool output so one result can't eat the model's small context window.
func clip(_ s: String, _ limit: Int = 1200) -> String {
    s.count <= limit ? s : String(s.prefix(limit)) + "\n[output truncated]"
}

func log(_ s: String) {
    FileHandle.standardError.write(Data((s + "\n").utf8))
}

/// Run a shell command from the project root. Output is merged stdout+stderr.
func shell(_ command: String, timeout: TimeInterval = 120) -> (status: Int32, output: String) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/zsh")
    p.arguments = ["-c", command]
    p.currentDirectoryURL = root
    // No .pyc: Python invalidates by mtime (1s) + size, so a quick same-size edit can
    // make a check run the OLD code.
    var env = ProcessInfo.processInfo.environment
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p.environment = env
    let pipe = Pipe()
    p.standardOutput = pipe
    p.standardError = pipe
    do { try p.run() } catch { return (-1, "failed to launch: \(error)") }
    let killer = DispatchWorkItem { if p.isRunning { p.terminate() } }
    DispatchQueue.global().asyncAfter(deadline: .now() + timeout, execute: killer)
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    killer.cancel()
    let out = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    return (p.terminationStatus, out)
}

/// The user-defined definition of "done". Runs without an approval prompt because the
/// user wrote it, not the model.
struct Check: Sendable {
    let command: String

    func run() -> (passed: Bool, report: String) {
        let r = shell(command)
        let report = clip("$ \(command)\nexit \(r.status)\n\(r.output)")
        return (r.status == 0, report)
    }

    /// Appended to every edit tool's output so the model sees the result immediately.
    func suffix() -> String {
        let r = run()
        return "\nCheck \(r.passed ? "PASSED" : "FAILED"):\n\(r.report)"
    }
}
