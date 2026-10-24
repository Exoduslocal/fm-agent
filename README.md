# fm-agent

A small coding-agent harness for the on-device model that ships with Apple Intelligence (the one behind the `fm` command and the Foundation Models framework). You give it a task and a check command. It reads and edits files in the current directory, runs your check after every edit, and stops when the check passes.

There are two implementations with the same behavior:

- `fm_agent.py`: Python, standard library only. Talks to `fm serve`.
- `swift/`: Swift, using the Foundation Models framework directly with real `Tool` / `@Generable` tool calling.

This is experimental. The model is small (about 3B parameters, 4096-token context), so the harness is mostly guardrails around it. Read the [benchmarks](#benchmarks) before relying on it: on small files it does not beat just asking the model once.

## Contents

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Safety](#safety)
- [Benchmarks](#benchmarks)
- [How it works, and what the model gets wrong](#how-it-works-and-what-the-model-gets-wrong)
- [Limitations](#limitations)
- [Repository layout](#repository-layout)

## Requirements

- An Apple silicon Mac with Apple Intelligence enabled. `fm available` should print `System model available`.
- Python implementation: Python 3 with no third-party packages. It uses `Path.is_relative_to`, so 3.9 or newer; I only tested 3.14.
- Swift implementation: Xcode with Swift 6.2 or newer (`Package.swift` uses tools version 6.2).
- Python 3 is also needed at runtime by the Swift implementation's Python-specific guards. Without it those guards turn into no-ops.

Everything was developed and measured on one machine: Apple M2 Pro, 16 GB, macOS 27.0.1, Xcode 27 (Swift 6.4), Python 3.14.2. I have not run it on macOS 26. The Swift code checks `#available(macOS 27.0, *)` around the one macOS 27 API it uses, so it should build for 26, but that is untested.

## Quick start

Both versions are run from inside the project you want them to work on.

### Python

```sh
cd path/to/your/project
python3 /path/to/fm-agent/fm_agent.py \
  --check "python3 test_stats.py" \
  "stats.py has bugs and test_stats.py fails. Fix the bugs in stats.py."
```

If `fm serve` is not already running, the script starts it on `127.0.0.1:1976` and stops it when it exits.

### Swift

```sh
cd /path/to/fm-agent/swift
swift build -c release

cd path/to/your/project
/path/to/fm-agent/swift/.build/release/fm-agent \
  --check "python3 test_stats.py" \
  "stats.py has bugs and test_stats.py fails. Fix the bugs in stats.py."
```

Copy `.build/release/fm-agent` somewhere on your `PATH` if you want to call it by name.

## Usage

```
fm_agent.py [-v] [--check CMD] "task"
fm-agent    [--check CMD] [--rounds N] "task"
```

| Option | Applies to | Meaning |
|---|---|---|
| `--check CMD` | both | A shell command that defines "done". Exit status 0 means done. See below. |
| `-v`, `--verbose` | Python | Log every model call with its duration. |
| `--rounds N` | Swift | Maximum number of model turns (default 6). |

The Python version stops after 15 tool calls (`MAX_STEPS` in the file).

### The check command

`--check` is the most important option. Without it the harness has no way to know whether the model's work is right, and the model is quick to say it is finished when it is not.

With `--check`:

1. The check runs once before anything else. If it already passes, the harness exits. Otherwise the failure output is shown to the model as the starting point.
2. The check runs automatically after every file edit, and its output goes back to the model.
3. The harness stops the moment the check exits 0.
4. If the model says it is done but the check still fails, the harness does not accept that.

Good checks print a useful failure message, because the model reads it. A test file with assertion messages works well. A check that only exits 1 with no output gives the model nothing to work from. Use a diff against expected output for generated output, or your test runner for code.

The harness reports success only when your check passes. If your check is weak, "passed" is weak too. In the benchmark below, a visible check passed while hidden tests failed in 13 of 80 Python harness runs.

Exit status is 0 when the check passed and non-zero otherwise.

### Tools the model can use

| Tool | What it does |
|---|---|
| `list_dir` | List a directory. |
| `read_file` | Read a file with line numbers. |
| `write_file` | Create or overwrite a file. The model gives only the path; the contents are generated separately (see [why](#how-it-works-and-what-the-model-gets-wrong)). |
| `edit_lines` | Replace a small range of lines (at most 8) in an existing file. The model chooses the lines; the replacement is generated separately. |
| `run_command` | Run a shell command. Asks you `[y/N]` every time. |

### Use it for bigger files, not small ones

The benchmark shows the harness only pays off when the file is too large to rewrite in one shot. For a short file, asking the model once is just as good and several times faster:

```sh
fm respond -i "Reply with one fenced code block containing the complete file." "..."
```

## Safety

- **Not a sandbox.** File tools refuse paths outside the current directory (symlinks are resolved first), but your `--check` command and any `run_command` you approve run as you, with your permissions.
- **`--check` is not asked about.** You wrote it, so it runs without a prompt, including after every edit. Do not pass a check you would not run yourself.
- **`run_command` asks every time.** If stdin is closed (CI, scripts), commands are denied.
- **`fm serve` has no authentication.** The Python harness starts it bound to `127.0.0.1` on purpose. If you start your own `fm serve` and leave out `--host`, I did not verify what it listens on by default, so pass `--host 127.0.0.1`.
- **It edits your files in place.** Run it in a git repository so you can review and revert.
- The model runs on your device. Nothing here sends code to a remote service.

## Benchmarks

### Setup

I wanted to know whether the harness adds anything over calling the model once, and how reliable it is. So there are three arms:

| Arm | What it does |
|---|---|
| **Baseline (one shot)** | One call to `fm respond`. The prompt contains the task, plus the target file and the failing check output for tasks that start with a file. The fenced code block that comes back is written to the target file. No tools, no retries, no feedback. |
| **Python harness** | `fm_agent.py --check ...` |
| **Swift harness** | `fm-agent --check ...` (release build) |

There are 8 tasks, 10 trials per task per arm, 240 trials in total. Every trial starts in a fresh temporary copy of the task's files. The harnesses get the same task text and the same `--check` command.

Scoring is done by the benchmark runner, not by the agent:

- **Held-out tests (headline number).** After the agent finishes, the runner copies in a second set of tests that the agent never saw and runs them. These catch fixes that satisfy the visible test but are wrong, for example hard-coding the bounds from a test case.
- **Visible check.** The `--check` command the agent was given, run again by the runner.

An agent saying it succeeded counts for nothing. In every harness run where the agent exited 0, the runner's own run of the visible check also passed (80 of 80 for Python, 71 of 71 for Swift).

`run_command` is denied during the benchmark (stdin is closed), so the only command that executes is the check. Each trial is killed after 180 seconds and counts as a failure. The model uses its default sampling settings, so trials are not deterministic.

### Tasks

Each task was validated before any model ran: the starting files must fail the visible check, and a reference solution must pass both the visible and the held-out tests (`python3 bench/run.py --selftest`).

| Task | Split | What the model has to do |
|---|---|---|
| `fizzbuzz` | dev | Create `fizz.py` from a one-line spec. Output is fully specified, so there are no held-out tests. |
| `fix-stats` | dev | Fix three independent bugs in a 3-function file. |
| `fix-one-bug` | dev | Find and fix one bug among three functions, without breaking the others. |
| `create-slugify` | dev | Create `slugify.py` from a prose spec. |
| `add-function` | dev | Add `median` to an existing correct module without changing the other functions. |
| `fix-chunk` | fresh | Fix an off-by-one in one function of a 3-function module. |
| `create-roman` | fresh | Create `roman.py` converting integers to Roman numerals. |
| `fix-large` | scale | Fix one bug in a 498-line, about 3,400-token module. |

The splits matter. **dev** tasks are the ones I looked at while building and fixing the harness, so the harness is tuned to them and their numbers are optimistic. **fresh** tasks were written after the tuning and never used for it. The **scale** task was added after the first full run showed that the small tasks could not separate the arms (see the results). A one-shot rewrite of `fix-large` needs the file in the prompt and again in the reply, which is over 6,000 tokens against the 4,096-token window, so it cannot fit.

### Results

Held-out pass rate, shown as passes/trials (rate) with a 95% Wilson confidence interval in brackets.

| | Baseline (one shot) | Python harness | Swift harness |
|---|---|---|---|
| **All 8 tasks** | 59/80 (74%) [63–82%] | 67/80 (84%) [74–90%] | 62/80 (78%) [67–85%] |
| 7 small tasks | 59/70 (84%) [74–91%] | 60/70 (86%) [76–92%] | 55/70 (79%) [68–87%] |
| `fix-large` only | **0/10 (0%) [0–28%]** | **7/10 (70%) [40–89%]** | **7/10 (70%) [40–89%]** |

Per task:

| Task | Baseline | Python harness | Swift harness |
|---|---|---|---|
| fizzbuzz (dev) | 8/10 | 10/10 | 10/10 |
| fix-stats (dev) | 10/10 | 10/10 | 10/10 |
| fix-one-bug (dev) | 10/10 | 9/10 | 10/10 |
| create-slugify (dev) | 1/10 | 1/10 | 0/10 |
| add-function (dev) | 10/10 | 10/10 | 6/10 |
| fix-chunk (fresh) | 10/10 | 10/10 | 10/10 |
| create-roman (fresh) | 10/10 | 10/10 | 9/10 |
| fix-large (scale) | 0/10 | 7/10 | 7/10 |
| **Dev tasks** | 39/50 (78%) | 40/50 (80%) | 36/50 (72%) |
| **Fresh tasks** | 20/20 (100%) | 20/20 (100%) | 19/20 (95%) |

Visible check pass rate (the tests the agent is given):

| | Baseline | Python harness | Swift harness |
|---|---|---|---|
| All 8 tasks | 67/80 (84%) [74–90%] | 80/80 (100%) [95–100%] | 71/80 (89%) [80–94%] |

Cost, over all 80 trials per arm:

| | Baseline | Python harness | Swift harness |
|---|---|---|---|
| Median time per trial | 3 s | 6 s | 7 s |
| 90th percentile | 12 s | 21 s | 99 s |
| Mean tool calls | 1 | 2.5 | 10.2 |
| Hit the 180 s limit | 0 | 0 | 7 |
| Pass visible, fail held-out | 8 | 13 | 9 |

The full tables, every trial, and the log of each trial are in `bench/results/`.

### Reading the results

- **On small files the harness does not help.** On the 7 small tasks the baseline scores 84%, Python 86% and Swift 79%, and the intervals overlap almost completely. A file that fits in the context window can be rewritten in one go, which is faster and as accurate.
- **On a file too big to rewrite, it does.** The baseline fails every time, and all 10 baseline logs show `The session's transcript exceeded the model's context size`. Both harnesses fix the bug in 7 of 10 trials. The harnesses never put the whole file in a prompt: they show the model only the function the traceback points at and replace a few lines, which is consistent with the result, though I did not test that cause in isolation. The misses are informative: all 3 Python failures, and 1 of Swift's 3, fixed the main case but failed the same held-out edge case (`rotate_list([], 0)`); Swift's other 2 hit the time limit. With 10 trials the interval is wide (40–89%), so the 70% figure is rough, but the gap from 0% is not in doubt. This is a single task, so it shows the harness can handle a big file, not that it will on yours.
- **The check loop does what it is for.** Python met the visible check in 80 of 80 trials against 67 of 80 for the baseline.
- **Meeting the check is not the same as being right.** `create-slugify` accounts for almost all of the gap between the visible and held-out columns. The spec says "characters that are not letters or digits". The held-out tests include `slugify("A_B") == "a-b"`. All 28 trials that failed the held-out tests failed on that one assertion, in all three arms (the 2 that passed, one baseline and one Python harness, handled the underscore). When I sampled the baseline's code for this task, it used regexes like `[^\w]`, which treat `_` as a word character; I did not read the code of every failing trial. The visible tests do not cover underscores, so nothing told any arm it was wrong. That is what a held-out test is for, and a reminder to write checks that cover what you care about.
- **Python and Swift are not distinguishable here.** 84% against 78% overall, with overlapping intervals. Swift is slower and has a long tail: 7 of its 80 trials ran into the 180-second limit, in four different tasks. The Python harness had none.

### Caveats

- **Small samples.** Ten trials per cell. Per-task numbers can swing by several points between reruns, and I have not run repeats of the whole benchmark.
- **One machine, one day.** The on-device model is updated with the OS, and I cannot see its version.
- **The harness changed during the work.** Tuning on the dev tasks is the reason for the dev/fresh split. After the first full run I also found and fixed two bugs in the Swift version using the `fix-large` logs (it did not stop when the check passed, and it did not recognize one form of the context-overflow error), then reran the whole Swift arm. The Swift numbers above are from the final code. The Python harness changed after its first seven tasks were run in two small ways: it now allows editing files over 5,000 characters when it can tell which function failed (only `fix-large` is that big, and it ran after the change), and it binds `fm serve` to `127.0.0.1` explicitly. Neither changes behavior on the other seven tasks.
- **I found one mistake in my own test, before running models.** The self-test caught a wrong expected value in `fix-large` (a vowel count of 4 that should be 3), which would have made every arm fail for the wrong reason.
- **Small, synthetic tasks.** They are 10 to 500 lines of Python with one or three bugs. They say little about real repositories, other languages, or multi-file changes. The Python-specific guards (below) do nothing for other languages.
- **The baseline is a plain one-shot rewrite.** A better baseline (several samples, retry on failure) would do better than what is shown here.

### Reproducing it

```sh
cd swift && swift build -c release && cd ..
python3 bench/run.py --selftest          # validates the tasks, runs no model
python3 bench/run.py -n 10               # about an hour on the machine above
python3 bench/run.py --report            # rebuild the tables from bench/results/runs.jsonl
```

Useful options: `--arms baseline,python,swift`, `--tasks fizzbuzz,fix-stats`, `--out DIR`. Results are appended to `runs.jsonl` after every trial, so an interrupted run continues where it stopped when you run the same command again. Close other heavy programs while it runs, since the timings depend on the machine. To add a task, create `bench/tasks/<name>/` with `task.json`, `seed/`, an optional `hidden/`, and a `solution/`; the self-test checks it.

## How it works, and what the model gets wrong

The model is small, so most of the code is working around specific behavior I measured. These notes might save you time if you build something similar.

Each step the model picks a tool, and the tool does its work. The ideas that made the difference:

- **`fm serve` ignores the OpenAI `tools` field.** The model answers in prose. `response_format` with a JSON schema is honored, so the Python version forces structured output: one call picks a tool from an enum, and a separate call fills in each argument. One big schema with every field made the model fill arguments before choosing the tool.
- **Free-text string fields can run away.** Asking the model to copy exact lines into a JSON string made it generate for about 70 seconds until the context filled, then fail with HTTP 500. `max_tokens` and a schema `maxLength` did not stop it. This also explained random 500 errors earlier. Fields that are integers or enums cannot run on, so edits choose line numbers instead of copying text.
- **`fm serve` handles one request at a time and keeps generating for abandoned ones.** Timing out and retrying only queues more work. The harness does not retry on a timeout.
- **Code inside a structured argument comes out worse than a fenced block.** With `content` as a tool argument the model collapsed code onto one line. Asked for "raw output, no fences" it produced junk (0 of 6 compiled). Asked for one fenced code block, it compiled 6 of 6. So `write_file` and `edit_lines` take only a path or a line range, and the tool generates the text separately as a fenced block and extracts it.
- **The model strips indentation inside a fence** (it returned `return x` for an indented line every time), so replacements are re-indented to match the line they replace. It also copies the `12:` line-number prefixes it sees from `read_file`, which are stripped.
- **It cannot find the bug from a traceback.** Left to pick lines from a whole file, it chose already-fixed code about 3 times in 5. The harness reads the traceback itself, works out which function failed, and shows and allows edits to only that function.
- **It declares success on wrong output.** This is why the check is the judge and the model's own "done" is never trusted.
- **Edits are guarded.** An edit is rejected, with the reason fed back to the model, if the file would stop parsing, if it would delete a function or class, or if it spans more than 8 lines (bigger spans got destructive).
- **The context window is about 4,096 tokens.** 4,000 worked and 6,000 did not. History is trimmed, tool output is truncated, and the Swift version starts a fresh session when it overflows.
- **Python bytecode caches can hide an edit.** A same-second, same-size edit (`lo` to `hi`) made a check run the old code. Checks run with `PYTHONDONTWRITEBYTECODE=1`.

The Python-specific guards (parse check, deleted-definition check, failure localization) use Python's `ast` module and only apply to `.py` files. Other files get the generic loop without them.

## Limitations

- Python source is the only language with the stronger guards.
- Single-file edits work best. Multi-file tasks are untested.
- Files over about 5,000 characters can only be edited when the check output names the failing function.
- The Swift version is slower and less consistent than the Python one in these measurements.
- Failing tasks can burn time: there is a step limit, but no cost limit beyond the 4,096-token window.
- No LICENSE file yet. Add one before reusing this code.

## Repository layout

```
fm_agent.py            Python harness
swift/                 Swift package (Package.swift, Sources/fm-agent/)
  App.swift            argument parsing, session loop, overflow handling
  Tools.swift          the five tools
  Guards.swift         parse / deletion / localization guards
  Environment.swift    path safety, shell runner, the check
bench/
  run.py               benchmark runner and report generator
  tasks/<name>/        task.json, seed/, hidden/, solution/
  results/             REPORT.md, runs.jsonl, env.json, logs/
```
