import Foundation

// Deterministic guards that sit between the model's edits and the disk. They exist
// because measured behavior of the ~3B on-device model showed it will, left alone:
//   * write a bare `return` at module level / duplicate a function nine times,
//   * "fix" already-fixed code instead of the code the failing check points at,
//   * re-read and re-edit the same lines in a loop.
// Python-specific checks shell out to python3's `ast`; if python3 is missing they
// degrade to no-ops rather than blocking edits.

/// Thrown by an edit tool to end the model session the moment the user's check passes.
/// Measured: if we wait for the model to finish its turn instead, it often ignores
/// "you are finished" and keeps calling tools until the context window overflows.
/// A thrown tool error aborts `respond()`; the app recognizes this one and re-runs the
/// check itself before declaring success.
struct CheckPassed: Error {}

/// Shared mutable state for the tools (tools are Sendable structs).
actor AgentState {
    var lastCheck = ""
    private(set) var checkPassed = false
    func setPassed(_ p: Bool) { checkPassed = p }
    /// Successful file changes so far. Lets the loop notice a round that only talked.
    private(set) var edits = 0
    private var readSinceEdit = Set<String>()

    func noteEdit() { edits += 1 }

    func setCheck(_ s: String) { lastCheck = s }

    /// True the first time a path is read since the last edit; false for a repeat.
    func markRead(_ path: String) -> Bool { readSinceEdit.insert(path).inserted }
    func resetReads() { readSinceEdit.removeAll() }
}

let maxEditSpan = 8  // bigger spans got destructive in testing

private let helperScript = #"""
import ast, json, os, re, sys

mode, path = sys.argv[1], sys.argv[2]
src = open(path).read()

def funcs(tree):
    return [(n.name, n.lineno, n.end_lineno) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

if mode == "syntax":
    try:
        compile(src, path, "exec")
    except SyntaxError as e:
        print(f"SyntaxError: {e.msg} (line {e.lineno}): {e.text!r}")
elif mode == "names":
    try:
        tree = ast.parse(src)
        print("\n".join(sorted({n.name for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))})))
    except SyntaxError:
        pass
elif mode == "focus":
    out = open(sys.argv[3]).read()
    try:
        fs = funcs(ast.parse(src))
    except SyntaxError:
        sys.exit(0)
    ranges = set()
    for m in re.finditer(r'File "([^"]+)", line (\d+)', out):
        if os.path.basename(m.group(1)) == os.path.basename(path):
            ln = int(m.group(2))
            ranges |= {(s, e, n) for n, s, e in fs if s <= ln <= e}
    if not ranges:
        ranges = {(s, e, n) for n, s, e in fs if re.search(r"\b" + re.escape(n) + r"\b", out)}
    if len(ranges) == len(fs) and len(fs) > 1:
        ranges = set()  # everything implicated: no information
    for s, e, n in sorted(ranges):
        print(s, e, n)
"""#

enum Guards {
    /// Run the embedded python helper. Returns nil if python3 isn't usable.
    private static func python(_ mode: String, file: URL, extra: String? = nil) -> String? {
        let tmp = FileManager.default.temporaryDirectory
        let helper = tmp.appendingPathComponent("fm_agent_helper.py")
        if (try? helperScript.write(to: helper, atomically: true, encoding: .utf8)) == nil { return nil }
        var cmd = "python3 \(quote(helper.path)) \(mode) \(quote(file.path))"
        if let extra { cmd += " \(quote(extra))" }
        let r = shell(cmd, timeout: 20)
        return r.status == 0 ? r.output : nil
    }

    private static func quote(_ s: String) -> String { "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }

    private static func candidate(_ text: String) -> URL? {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("fm_agent_candidate.txt")
        return (try? text.write(to: url, atomically: true, encoding: .utf8)) == nil ? nil : url
    }

    /// nil when fine (or unchecked).
    static func syntaxError(for url: URL, text: String) -> String? {
        switch url.pathExtension {
        case "py":
            guard let c = candidate(text), let out = python("syntax", file: c), !out.isEmpty else { return nil }
            return out
        case "json":
            do { _ = try JSONSerialization.jsonObject(with: Data(text.utf8)); return nil }
            catch { return "Invalid JSON: \(error.localizedDescription)" }
        default:
            return nil
        }
    }

    /// Names of functions/classes that `old` defines and `new` doesn't.
    static func deletedDefinitions(url: URL, old: String, new: String) -> [String] {
        guard url.pathExtension == "py",
              let a = candidate(old), let before = python("names", file: a) else { return [] }
        guard let b = candidate(new), let after = python("names", file: b) else { return [] }
        let kept = Set(after.split(separator: "\n").map(String.init))
        return before.split(separator: "\n").map(String.init).filter { !kept.contains($0) }
    }

    struct Focus { let start: Int; let end: Int; let name: String }

    /// Functions in `url` that the check output points at (traceback frame, else name mention).
    static func focus(url: URL, checkOutput: String) -> [Focus] {
        guard url.pathExtension == "py", !checkOutput.isEmpty else { return [] }
        let outFile = FileManager.default.temporaryDirectory.appendingPathComponent("fm_agent_check.txt")
        guard (try? checkOutput.write(to: outFile, atomically: true, encoding: .utf8)) != nil,
              let out = python("focus", file: url, extra: outFile.path) else { return [] }
        return out.split(separator: "\n").compactMap { line in
            let p = line.split(separator: " ", maxSplits: 2).map(String.init)
            guard p.count == 3, let s = Int(p[0]), let e = Int(p[1]) else { return nil }
            return Focus(start: s, end: e, name: p[2])
        }
    }

    /// A pointer for the model: which function in which top-level .py file the failure is in.
    static func hint(checkOutput: String) -> String? {
        let files = ((try? FileManager.default.contentsOfDirectory(atPath: root.path)) ?? [])
            .filter { $0.hasSuffix(".py") }.sorted()
        for f in files {
            let ranges = focus(url: root.appendingPathComponent(f), checkOutput: checkOutput)
            if !ranges.isEmpty {
                let desc = ranges.map { "\($0.name) (lines \($0.start)-\($0.end))" }.joined(separator: ", ")
                return "Hint: the failure points at \(desc) in \(f). Only edit that code."
            }
        }
        return nil
    }
}

/// Run the check after an edit; record it for the guards; format it for the model.
func afterEdit(check: Check?, state: AgentState) async -> String {
    await state.resetReads()  // the file changed, so a re-read is legitimate again
    await state.noteEdit()
    guard let check else { return "" }
    let r = check.run()
    await state.setCheck(r.report)
    await state.setPassed(r.passed)
    var s = "\nCheck \(r.passed ? "PASSED" : "FAILED"):\n\(r.report)"
    if !r.passed, let h = Guards.hint(checkOutput: r.report) { s += "\n\(h)" }
    return s
}
