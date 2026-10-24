import Foundation
import FoundationModels

// Real tool calling: each tool is a `Tool` whose `Arguments` is `@Generable`, so the model
// is constrained to produce valid, typed arguments. Tools never throw for expected
// failures; they return the error as text so the model can recover (a thrown error would
// abort the whole respond() call). Edits pass through the guards in Guards.swift first.

/// read_file shows `12: code`. Measured: the model copies those prefixes into what it
/// writes back, which then fails to parse. Strip them, but only when EVERY non-empty
/// line has one, so real code like `3: x` inside a dict literal is left alone.
func stripLineNumbers(_ text: String) -> String {
    let lines = text.components(separatedBy: "\n")
    let nonEmpty = lines.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    let prefix = #/^\s*\d+: ?/#
    guard !nonEmpty.isEmpty, nonEmpty.allSatisfy({ $0.firstMatch(of: prefix) != nil }) else { return text }
    return lines.map { $0.replacing(prefix, with: "", maxReplacements: 1) }.joined(separator: "\n")
}

struct ListDirTool: Tool {
    let name = "list_dir"
    let description = "List the files in a directory of the project."

    @Generable
    struct Arguments {
        @Guide(description: "Relative directory path. Use . for the project root.")
        var path: String
    }

    func call(arguments: Arguments) async throws -> String {
        log("  [list_dir] \(arguments.path)")
        do {
            let url = try safePath(arguments.path.isEmpty ? "." : arguments.path)
            let names = try FileManager.default.contentsOfDirectory(atPath: url.path)
                .filter { !$0.hasPrefix(".") && $0 != "__pycache__" }.sorted()
            return names.isEmpty ? "(empty)" : names.joined(separator: "\n")
        } catch { return "error: \(error)" }
    }
}

struct ReadFileTool: Tool {
    let name = "read_file"
    let description = "Read a file. Lines are numbered so edit_lines can refer to them."
    let state: AgentState

    @Generable
    struct Arguments {
        @Guide(description: "Relative path of an existing file, like app.py")
        var path: String
    }

    func call(arguments: Arguments) async throws -> String {
        log("  [read_file] \(arguments.path)")
        do {
            let url = try safePath(arguments.path)
            // Re-reading an unchanged file only burns the 4k-token window.
            guard await state.markRead(url.path) else {
                return "You already read \(arguments.path) and it has not changed since. Its contents are above."
            }
            guard FileManager.default.fileExists(atPath: url.path) else {
                return "error: \(arguments.path) does not exist. Create it with write_file."
            }
            let text = try String(contentsOf: url, encoding: .utf8)
            let numbered = text.components(separatedBy: "\n").enumerated()
                .map { "\($0.offset + 1): \($0.element)" }.joined(separator: "\n")
            return clip(numbered, 3000)
        } catch { return "error: could not read \(arguments.path)" }
    }
}

/// The file's contents are NOT a tool argument. Measured: when the model had to put code
/// inside a structured string argument it collapsed it onto one line
/// (`print('FizzBuzz') for i in range(1, 16): ...`), which doesn't parse. As a fenced
/// code block in plain generation it is reliable. So the tool takes only a path and
/// generates the body itself in a fresh, small session.
struct WriteFileTool: Tool {
    let name = "write_file"
    let description = "Create a new file, or completely overwrite one. Give only the path; the contents are written for you from the task. For small fixes to an existing file use edit_lines instead."
    let check: Check?
    let state: AgentState
    let task: String

    @Generable
    struct Arguments {
        @Guide(description: "Relative file name like app.py. Never absolute, never a directory.")
        var path: String
    }

    func call(arguments: Arguments) async throws -> String {
        log("  [write_file] \(arguments.path)")
        let result = await run(arguments)
        log("    -> " + result.split(separator: "\n", maxSplits: 1).first.map(String.init)!.prefix(150))
        if await state.checkPassed { throw CheckPassed() }
        return result
    }

    private func run(_ arguments: Arguments) async -> String {
        do {
            let url = try safePath(arguments.path)
            var isDir: ObjCBool = false
            if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir), isDir.boolValue || arguments.path == "." {
                return "error: \(arguments.path) is a directory. Give a file name like app.py."
            }
            let existing = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            var feedback = await state.lastCheck
            var content = ""
            var problem: String?
            for _ in 0..<3 {  // regenerate with the parser's complaint until it parses
                content = try await generateContents(path: arguments.path, existing: existing, feedback: feedback)
                problem = Guards.syntaxError(for: url, text: content)
                guard let p = problem else { break }
                feedback = p
            }
            if let problem { return "error: file not written, it would not parse: \(problem)" }
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try content.write(to: url, atomically: true, encoding: .utf8)
            return "wrote \(arguments.path)" + (await afterEdit(check: check, state: state))
        } catch { return "error: \(error)" }
    }

    private func generateContents(path: String, existing: String, feedback: String) async throws -> String {
        var prompt = "\(task)\n\nWrite the complete file `\(path)`."
        if !existing.isEmpty { prompt += "\n\nCurrent contents:\n\(String(existing.prefix(4000)))" }
        if !feedback.isEmpty { prompt += "\n\nFix this problem:\n\(String(feedback.prefix(1200)))" }
        let session = LanguageModelSession(
            model: .default,
            instructions: "You are an expert programmer. Reply with exactly one fenced code block containing the complete file, and nothing else.")
        let reply = try await session.respond(to: prompt).content
        return extractFence(reply)
    }
}

/// Body of the first ``` fence, or the whole reply if there isn't one.
func extractFence(_ text: String) -> String {
    if let m = text.firstMatch(of: #/```[\w+-]*\n(.*?)```/#.dotMatchesNewlines()) {
        return String(m.output.1).trimmingCharacters(in: .whitespacesAndNewlines) + "\n"
    }
    return text.trimmingCharacters(in: .whitespacesAndNewlines) + "\n"
}

/// Like extractFence but keeps the first line's indentation (only leading blank lines and
/// trailing whitespace go). Needed for edits: trimming would strip the indent of line one
/// while later lines keep theirs, and re-indenting would then over-indent the rest.
func extractFenceKeepingIndent(_ text: String) -> String {
    var body = text
    if let m = text.firstMatch(of: #/```[\w+-]*\n(.*?)```/#.dotMatchesNewlines()) { body = String(m.output.1) }
    var lines = body.components(separatedBy: "\n")
    while let f = lines.first, f.trimmingCharacters(in: .whitespaces).isEmpty { lines.removeFirst() }
    while let l = lines.last, l.trimmingCharacters(in: .whitespaces).isEmpty { lines.removeLast() }
    return lines.joined(separator: "\n")
}

/// The replacement text is NOT a tool argument. Measured: given a structured `newText`
/// argument the model dropped the `def` line while targeting it, then repeated the same
/// rejected edit 34 times. The model only chooses WHERE (file + line range); the tool
/// writes WHAT in a fresh session, as a fenced block, from the task and the failing check.
struct EditLinesTool: Tool {
    let name = "edit_lines"
    let description = "Fix a few lines of an existing file: replaces lines startLine through endLine (inclusive, numbered as read_file shows them). Do not supply the new code; it is written for you from the task and the failing check. Keep the range to \(maxEditSpan) lines or fewer. Read the file first."
    let check: Check?
    let state: AgentState
    let task: String

    @Generable
    struct Arguments {
        @Guide(description: "Relative path of an existing file")
        var path: String
        @Guide(description: "First line number to replace", .range(1...2000))
        var startLine: Int
        @Guide(description: "Last line number to replace", .range(1...2000))
        var endLine: Int
    }

    func call(arguments a: Arguments) async throws -> String {
        log("  [edit_lines] \(a.path) \(a.startLine)-\(a.endLine)")
        let result = await run(a)
        log("    -> " + result.split(separator: "\n", maxSplits: 1).first.map(String.init)!.prefix(150))
        if await state.checkPassed { throw CheckPassed() }
        return result
    }

    private func run(_ a: Arguments) async -> String {
        do {
            let url = try safePath(a.path)
            guard FileManager.default.fileExists(atPath: url.path) else {
                return "error: \(a.path) does not exist, so there is nothing to edit. Create it with write_file."
            }
            let original = try String(contentsOf: url, encoding: .utf8)
            var lines = original.components(separatedBy: "\n")
            guard a.startLine >= 1, a.startLine <= a.endLine, a.endLine <= lines.count else {
                return "error: lines \(a.startLine)-\(a.endLine) are out of range; the file has \(lines.count) lines."
            }
            guard a.endLine - a.startLine + 1 <= maxEditSpan else {
                return "error: edit rejected, \(a.endLine - a.startLine + 1) lines is too many. Replace at most \(maxEditSpan) lines at a time."
            }
            // If the failure points at specific functions, edits must touch them.
            let focus = Guards.focus(url: url, checkOutput: await state.lastCheck)
            if !focus.isEmpty, !focus.contains(where: { $0.start <= a.endLine && a.startLine <= $0.end }) {
                let where_ = focus.map { "\($0.name) (lines \($0.start)-\($0.end))" }.joined(separator: ", ")
                return "error: edit rejected, lines \(a.startLine)-\(a.endLine) are not part of the failure. The failing code is \(where_). Edit that instead."
            }

            let old = Array(lines[(a.startLine - 1)..<a.endLine])
            let replacement = try await generateReplacement(
                path: a.path, lines: lines, start: a.startLine, end: a.endLine, focus: focus)
            var new = stripLineNumbers(replacement).components(separatedBy: "\n")
            // Models often strip leading indentation inside a block. Shift the
            // replacement so its first line sits where the line it replaces sits.
            let want = indent(of: old[0]), got = indent(of: new[0])
            if !new[0].trimmingCharacters(in: .whitespaces).isEmpty, got.count < want.count {
                let shift = String(want.dropFirst(got.count))
                new = new.map { $0.trimmingCharacters(in: .whitespaces).isEmpty ? $0 : shift + $0 }
            }
            if new == old {
                return "error: edit rejected, the new lines are identical to the old ones. Pick the line that is actually wrong."
            }
            lines.replaceSubrange((a.startLine - 1)..<a.endLine, with: new)
            let updated = lines.joined(separator: "\n")

            if let err = Guards.syntaxError(for: url, text: updated) {
                return "error: edit rejected, it would break the file (\(err)). The lines you targeted were:\n\(old.joined(separator: "\n"))"
            }
            let lost = Guards.deletedDefinitions(url: url, old: original, new: updated)
            if !lost.isEmpty {
                return "error: edit rejected, it would delete \(lost.joined(separator: ", ")). Replace only the wrong lines."
            }
            try updated.write(to: url, atomically: true, encoding: .utf8)
            return "edited \(a.path) lines \(a.startLine)-\(a.endLine)" + (await afterEdit(check: check, state: state))
        } catch { return "error: \(error)" }
    }

    private func generateReplacement(path: String, lines: [String], start: Int, end: Int,
                                     focus: [Guards.Focus]) async throws -> String {
        // Show only the failing function(s) when we know them: smaller prompt, better aim.
        let visible: [Int] = focus.isEmpty
            ? Array(1...lines.count)
            : Array(Set(focus.flatMap { Array($0.start...$0.end) } + Array(start...end))).sorted()
        let numbered = visible.map { "\($0): \(lines[$0 - 1])" }.joined(separator: "\n")
        var prompt = "Task: \(task)"
        let lastCheck = await state.lastCheck
        if !lastCheck.isEmpty { prompt += "\n\nCheck output (the problem to fix):\n\(String(lastCheck.prefix(1200)))" }
        prompt += "\n\nFile `\(path)`:\n\(String(numbered.prefix(4000)))"
        prompt += "\n\nRewrite lines \(start) to \(end) with the problem fixed. Reply with one fenced code block containing only the new version of those lines, with the same indentation and without line numbers."
        let session = LanguageModelSession(
            model: .default,
            instructions: "You are an expert programmer. Reply with exactly one fenced code block, and nothing else.")
        return extractFenceKeepingIndent(try await session.respond(to: prompt).content)
    }

    private func indent(of line: String) -> String { String(line.prefix { $0 == " " || $0 == "\t" }) }
}

struct RunCommandTool: Tool {
    let name = "run_command"
    let description = "Run a shell command such as `python3 app.py` to run or test code. The user must approve each command."
    let hasCheck: Bool

    @Generable
    struct Arguments {
        @Guide(description: "A shell command, for example python3 app.py")
        var command: String
    }

    func call(arguments: Arguments) async throws -> String {
        let cmd = arguments.command.trimmingCharacters(in: .whitespacesAndNewlines)
        log("  [run_command] \(cmd)")
        // Human approval gate: the model should not run arbitrary shell unattended.
        FileHandle.standardError.write(Data("  run `\(cmd)`? [y/N] ".utf8))
        guard (readLine() ?? "").lowercased().hasPrefix("y") else {
            return "user denied the command."
                + (hasCheck ? " You do not need to run anything: the check runs automatically after every edit." : "")
        }
        let r = shell(cmd, timeout: 60)
        return clip("$ \(cmd)\nexit \(r.status)\n\(r.output)")
    }
}
