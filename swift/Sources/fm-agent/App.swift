import Foundation
import FoundationModels

// usage (run from the project directory the agent should work in):
//   fm-agent [--check CMD] [--rounds N] "task description"
//
//   --check CMD   Defines "done". Runs up front (so the model starts from the real
//                 failure), after every edit (inside the tools), and after each model
//                 turn. The agent stops when it exits 0; on failure the output is fed
//                 back as the next prompt. Exit status is 0 only on success.

let instructions = """
You are a coding agent working in a project directory. Use the tools to do the task.
Rules:
- Paths are relative to the project root. Never use absolute paths.
- To fix a bug in an existing file: read_file it, then edit_lines the few wrong lines.
- To make a new file, use write_file. Never write files with echo or redirects.
- Make one small edit at a time. Fix only what the check output points at.
- When a tool result says Check PASSED, you are finished: reply with one short sentence.
- If a check FAILED, read its output and fix the cause.
"""

/// macOS 27 reports an overflow as LanguageModelError.contextSizeExceeded; earlier SDKs
/// (and some paths) use GenerationError.exceededContextWindowSize. Handle both, and
/// look through a tool-call wrapper.
func isContextOverflow(_ error: Error) -> Bool {
    if #available(macOS 27.0, *) {
        if let e = error as? LanguageModelError, case .contextSizeExceeded = e { return true }
    }
    if let e = error as? LanguageModelSession.GenerationError, case .exceededContextWindowSize = e { return true }
    if let e = error as? LanguageModelSession.ToolCallError { return isContextOverflow(e.underlyingError) }
    // Measured: an overflow also surfaced as an error whose type matched none of the cases
    // above ("Provided 4,105 tokens, but the maximum allowed is 4,096."). Fall back to the
    // message so the agent recovers instead of crashing.
    let text = "\(error) \(error.localizedDescription)".lowercased()
    return text.contains("maximum allowed is") || text.contains("exceeded the model's context")
        || text.contains("context window") || text.contains("context size")
}

/// A tool throws CheckPassed to end the session as soon as the user's check passes.
func isCheckPassed(_ error: Error) -> Bool {
    if error is CheckPassed { return true }
    if let e = error as? LanguageModelSession.ToolCallError { return isCheckPassed(e.underlyingError) }
    return false
}

@main
struct App {
    static func main() async {
        var check: Check?
        var maxRounds = 6
        var words: [String] = []
        var args = CommandLine.arguments.dropFirst()
        while let a = args.popFirst() {
            switch a {
            case "--check": check = args.popFirst().map(Check.init(command:))
            case "--rounds": maxRounds = args.popFirst().flatMap(Int.init) ?? maxRounds
            default: words.append(a)
            }
        }
        guard !words.isEmpty else {
            log("usage: fm-agent [--check CMD] [--rounds N] \"task\"")
            exit(2)
        }
        let task = words.joined(separator: " ")

        let model = SystemLanguageModel.default
        guard case .available = model.availability else {
            log("model unavailable: \(model.availability)")
            exit(2)
        }

        let state = AgentState()
        let tools: [any Tool] = [
            ListDirTool(), ReadFileTool(state: state),
            WriteFileTool(check: check, state: state, task: task),
            EditLinesTool(check: check, state: state, task: task),
            RunCommandTool(hasCheck: check != nil),
        ]
        func newSession() -> LanguageModelSession {
            LanguageModelSession(model: model, tools: tools, instructions: instructions)
        }

        var prompt = task
        if let check {
            let first = check.run()
            if first.passed { print("check already passes; nothing to do"); exit(0) }
            print("initial check FAILED:\n\(first.report)")
            await state.setCheck(first.report)
            prompt = "\(task)\n\nThe check currently fails:\n\(first.report)"
            if let h = Guards.hint(checkOutput: first.report) { prompt += "\n\(h)" }
        }

        var session = newSession()
        for round in 1...maxRounds {
            log("[round \(round)]")
            let editsBefore = await state.edits
            do {
                let reply = try await session.respond(to: prompt)
                print("model: \(reply.content)")
            } catch {
                // The check is the judge, so before treating ANY error as fatal, run it.
                // An edit that made it pass may have happened before the error.
                if let check, isCheckPassed(error) || isContextOverflow(error) {
                    let r = check.run()
                    if r.passed { print("check passed after \(round) round(s)"); exit(0) }
                }
                guard isContextOverflow(error) else {
                    log("error (\(type(of: error))): \(error)")
                    exit(1)
                }
                // The window is ~4096 tokens. Start over with where we are now.
                log("  context window full; starting a fresh session")
                session = newSession()
                await state.resetReads()
                prompt = "\(task)\n\nYou already made some edits. Continue fixing what is still failing."
                if let check {
                    let r = check.run()
                    if r.passed { print("check passed after \(round) round(s)"); exit(0) }
                    await state.setCheck(r.report)
                    prompt += "\n\nLatest check:\n\(r.report)"
                    if let h = Guards.hint(checkOutput: r.report) { prompt += "\n\(h)" }
                }
                continue
            }

            guard let check else { exit(0) }  // no check: one turn is all we have
            let result = check.run()
            if result.passed { print("check passed after \(round) round(s)"); exit(0) }
            await state.setCheck(result.report)
            // Measured: the model sometimes reads files, says "I'll add X", and stops
            // without calling an edit tool. Say so plainly instead of repeating the prompt.
            let idle = await state.edits == editsBefore
            prompt = idle
                ? "You did not change any file, so the check is still failing. Describing a change does nothing: call write_file or edit_lines now.\n\(result.report)"
                : "The check is still failing. Fix the cause.\n\(result.report)"
            if let h = Guards.hint(checkOutput: result.report) { prompt += "\n\(h)" }
        }
        print("stopped: hit \(maxRounds) rounds")
        exit(1)
    }
}
