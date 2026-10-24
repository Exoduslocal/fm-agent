#!/usr/bin/env python3
"""Minimal coding-agent harness for Apple's on-device model via `fm serve`.

usage (run from the project directory you want the agent to work in):
    fm_agent.py [-v] [--check CMD] "task description"

    --check CMD   A command that defines "done". It runs once up front (so the model
                  starts from the real failure), automatically after every edit, and
                  when the model says it is done. The agent stops the moment it exits 0.
                  Exit status of this script is 0 only on success.
    -v            Log every model call with timings.

What the experiments showed, and how this file handles it:
  * `fm serve` ignores OpenAI-style `tools`, so we force structured output with
    response_format=json_schema and run the tools ourselves.
  * One big schema with every field made the model fill args before choosing the
    tool. So each step is several small calls: pick a tool (enum), then one call per
    argument.
  * File contents are a plain-text call, as a fenced code block. Asking for
    "raw output, no fences" made the model emit junk; fenced + extract is reliable.
  * FREE-TEXT STRING FIELDS CAN RUN AWAY. Asking the model to copy exact lines into a
    JSON string ("search/replace" style) generated for ~70s until the 4096-token
    context filled, then returned HTTP 500 "exceeded the model's context size".
    max_tokens and schema maxLength do not stop it. So edits never ask the model to
    copy text: it picks line NUMBERS (integer enums, so they cannot run away) and
    writes the replacement as a fenced block; we splice it in ourselves.
  * `fm serve` handles one request at a time and keeps generating for abandoned
    requests. Timing out and retrying just queues more work, so we don't.
  * The context window is ~4096 tokens (6000 fails). History is trimmed, and edit
    prompts show the model only the file it is editing.
  * The model happily declares success on wrong output, so --check is the judge.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = 1976
BASE = f"http://127.0.0.1:{PORT}"
ROOT = Path.cwd().resolve()  # the agent may only touch files under here
MAX_STEPS = 15
MAX_OBS = 1200          # chars of tool output fed back
MAX_PROMPT_FILE = 5000  # chars of a file shown to the model when editing it
MAX_EDIT_SPAN = 8       # most lines one edit may replace (bigger spans got destructive)
MAX_HISTORY = 6500      # chars of conversation kept (~2k tokens of the 4k window)
CALL_TIMEOUT = 150      # a runaway call fails with HTTP 500 after ~70s; this is a backstop
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".build", ".idea"}
VERBOSE = False

TOOLS = ["list_dir", "read_file", "write_file", "edit_lines", "run_command", "done"]
ARGS_FOR = {"list_dir": ["path"], "read_file": ["path"], "write_file": ["path"],
            "edit_lines": [], "run_command": ["command"], "done": []}


def obj(**props):
    return {"type": "object", "properties": props, "required": list(props)}


SYSTEM = """You are a coding agent working in a project directory. Each turn you pick one tool.

Tools:
- list_dir: path, a directory ("." for the project root)
- read_file: path of an existing file
- write_file: path, a RELATIVE file name like app.py. Creates a new file or overwrites one completely; the contents are written in a separate step.
- edit_lines: changes a few lines of an EXISTING file in place; the file and line numbers are chosen in separate steps. Use this to fix bugs in existing files.
- run_command: command, a shell command such as `python3 app.py`. Only for running or testing code.
- done: the task is finished and verified.

Rules:
- Create and edit files with write_file or edit_lines only. Never use echo, cat, or redirects to write files.
- Paths are relative to the project root. Never use absolute paths.
- Never repeat an action that already succeeded.
- Make one small edit at a time. Do not read a file again after you have already read it.
{check_rules}"""

CHECK_RULES = """- A check command runs automatically after every edit and its result is shown to you.
  You do not need to run it yourself. If it FAILED, fix the code using its output."""
NO_CHECK_RULES = """- After writing a file, run it once to check it works.
- If a run succeeds and the task is complete, call done. If it fails, fix the file."""

# Measured: asking for "raw output, no fences" made the model emit junk (0/6 compiled).
# Asking for one fenced block and extracting it compiled 6/6.
WRITER = """You are an expert programmer. Reply with exactly one fenced code block containing
the complete file, and nothing else."""

EDITOR = """You fix bugs in source files. You are shown a task, the output of a failing
check if there is one, and one file with line numbers."""

LANGS = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".swift": "Swift",
         ".sh": "shell", ".html": "HTML", ".css": "CSS", ".json": "JSON", ".md": "Markdown"}


# ---------- model access ----------

def ensure_server():
    def up():
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return True
        except Exception:
            return False

    if up():
        return None
    # Bind to loopback explicitly: `fm serve` has no authentication, so it must never be
    # reachable from the network.
    proc = subprocess.Popen(["fm", "serve", "--host", "127.0.0.1", "--port", str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if up():
            return proc
        time.sleep(0.2)
    proc.kill()
    sys.exit("fm serve did not start")


def chat(messages, schema=None, retries=4):
    payload = {"model": "system", "stream": False, "messages": messages}
    if schema:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "out", "schema": schema}}
    data = json.dumps(payload).encode()
    last = ""
    for attempt in range(retries):
        req = urllib.request.Request(f"{BASE}/v1/chat/completions", data,
                                     {"content-type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=CALL_TIMEOUT) as r:
                out = json.load(r)["choices"][0]["message"]["content"]
            if VERBOSE:
                print(f"      . model call {time.time() - t0:.1f}s ({len(out)} chars)", flush=True)
            return out
        except urllib.error.HTTPError as e:
            last = e.read().decode()[:200]  # e.g. a runaway call hitting the context limit
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            # Do NOT retry: the server is still busy generating for this request.
            sys.exit(f"model call timed out after {CALL_TIMEOUT}s ({type(e).__name__}). "
                     "The server may still be busy; restart `fm serve` and try again.")
        if VERBOSE:
            print(f"      . model call failed after {time.time() - t0:.1f}s "
                  f"(attempt {attempt + 1}): {last[:100]}", flush=True)
    sys.exit(f"fm server kept failing: {last}")


def ask_field(messages, field, hint=None, enum=None):
    """One structured call that returns a single string field."""
    prop = {"type": "string"}
    if enum:
        prop["enum"] = enum
    ask = messages + ([{"role": "user", "content": hint}] if hint else [])
    return json.loads(chat(ask, obj(**{field: prop})))[field]


def ask_int(messages, field, hint, choices):
    """One structured call that returns one of `choices` (an enum, so it can't run on)."""
    ask = messages + [{"role": "user", "content": hint}]
    prop = {"type": "integer", "enum": list(choices)}
    return int(json.loads(chat(ask, obj(**{field: prop})))[field])


def trim_history(messages):
    # Keep the system prompt + task; drop the oldest action/result pairs first.
    while sum(len(m["content"]) for m in messages) > MAX_HISTORY and len(messages) > 4:
        del messages[2:4]


# ---------- files ----------

def safe_path(p):
    p = p.strip()
    while p.startswith("./"):
        p = p[2:]
    full = (ROOT / p).resolve()
    if not full.is_relative_to(ROOT):
        raise ValueError(f"path {p!r} is outside the project. Use a relative path like app.py")
    return full


def list_files(limit=60):
    out = []
    for f in sorted(ROOT.rglob("*")):
        rel = f.relative_to(ROOT)
        if f.is_file() and not (set(rel.parts) & SKIP_DIRS) and not f.name.startswith("."):
            out.append(rel.as_posix())
        if len(out) >= limit:
            break
    return out


def extract_fence(text, keep_indent=False):
    m = re.search(r"```[\w+-]*\n(.*?)```", text, re.S)
    body = m.group(1) if m else text
    return (body.rstrip() if keep_indent else body.strip()) + "\n"


def defined_names(path, text):
    """Names of functions/classes defined in a Python file (empty set for other files)."""
    if path.suffix != ".py":
        return set()
    try:
        return {n.name for n in ast.walk(ast.parse(text))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    except SyntaxError:
        return set()


def focus_ranges(path, text, check_out):
    """Deterministic bug localization from the check output (Python files only).
    Returns sorted (start, end) 1-based line ranges of the functions the failure points
    at: first any traceback frame inside this file, else functions named in the output.
    Measured: left to pick lines from the whole file, the model chose already-fixed code
    ~3 times in 5. A 3B model can't localize from a traceback; this can."""
    if path.suffix != ".py" or not check_out:
        return []
    try:
        funcs = [(n.name, n.lineno, n.end_lineno) for n in ast.walk(ast.parse(text))
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    except SyntaxError:
        return []
    ranges = set()
    for m in re.finditer(r'File "([^"]+)", line (\d+)', check_out):
        if Path(m.group(1)).name == path.name:
            ln = int(m.group(2))
            ranges |= {(s, e) for _, s, e in funcs if s <= ln <= e}
    if not ranges:
        ranges = {(s, e) for name, s, e in funcs if re.search(rf"\b{re.escape(name)}\b", check_out)}
    if len(ranges) == len(funcs) and len(funcs) > 1:
        return []  # everything is implicated (e.g. an ImportError); no information
    return sorted(ranges)


def syntax_error(path, text):
    """Cheap deterministic check. Returns an error string, or '' if fine/unchecked."""
    if path.suffix == ".py":
        try:
            compile(text, str(path), "exec")
        except SyntaxError as e:
            return f"SyntaxError: {e.msg} (line {e.lineno}): {e.text!r}"
    elif path.suffix == ".json":
        try:
            json.loads(text)
        except ValueError as e:
            return f"Invalid JSON: {e}"
    return ""


def write_contents(task, path, existing, feedback):
    lang = LANGS.get(Path(path).suffix, "text")
    prompt = f"{task}\n\nWrite the complete {lang} file `{path}`."
    if existing:
        prompt += f"\n\nCurrent contents:\n{existing[:MAX_PROMPT_FILE]}"
    if feedback:
        prompt += f"\n\nFix this problem:\n{feedback}"
    return extract_fence(chat([{"role": "system", "content": WRITER},
                               {"role": "user", "content": prompt}]))


def number_lines(lines):
    return "\n".join(f"{i}: {l}" for i, l in enumerate(lines, 1))


def clean_replacement(reply):
    """Fenced block -> list of lines. Keeps indentation; drops echoed line numbers."""
    lines = extract_fence(reply, keep_indent=True).rstrip("\n").split("\n")
    if lines and all(re.match(r"^\d+:\s?", l) for l in lines if l.strip()):
        lines = [re.sub(r"^\d+:\s?", "", l, count=1) for l in lines]
    return lines


def reindent(new_lines, old_first_line):
    """The model usually strips leading indentation inside a fence (measured: it
    returned `return x` for an indented line, every time). Shift the replacement so
    its first line sits at the same indent as the line it replaces."""
    if not new_lines or not new_lines[0].strip():
        return new_lines
    want, got = indent_of(old_first_line), indent_of(new_lines[0])
    if len(got) >= len(want):
        return new_lines  # model kept (or deepened) the indent on purpose
    shift = want[len(got):]
    return [(shift + l if l.strip() else l) for l in new_lines]


def indent_of(line):
    return line[:len(line) - len(line.lstrip())]


# ---------- check ----------

def run_check(cmd):
    """Run the user-defined check. Returns (passed, output). No approval prompt: the
    user wrote this command, the model didn't."""
    # No .pyc files: Python invalidates them by mtime (1s resolution) + size, so a quick
    # same-size edit (`lo` -> `hi`) can make the check run the OLD code.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True,
                           timeout=120, env=env)
    except subprocess.TimeoutExpired:
        return False, f"$ {cmd}\ncheck timed out after 120s"
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0, f"$ {cmd}\nexit {r.returncode}\n{out}"[:MAX_OBS]


def after_edit(state):
    """Run the check after an edit and fold the result into the observation."""
    if not state["check"]:
        state["last_run"] = ""  # stale once the file changes
        return ""
    ok, out = run_check(state["check"])
    state["last_run"], state["check_ok"] = out, ok
    return f"\nCheck {'PASSED' if ok else 'FAILED'}:\n{out}"


# ---------- choosing and running tools ----------

def choose_action(messages, task, state):
    tool = ask_field(messages, "tool", enum=TOOLS)
    if tool == "edit_lines":
        return tool, choose_edit(messages, task, state)
    args = {}
    for field in ARGS_FOR[tool]:
        enum = list_files() if (tool == "read_file" and field == "path") else None
        args[field] = ask_field(messages, field, f"Tool: {tool}. Provide its {field}.",
                                enum or None).strip()
    return tool, args


def choose_edit(messages, task, state):
    files = list_files()
    if not files:
        return {"error": "no files exist yet. Create one with write_file."}
    path = ask_field(messages, "path", "Tool: edit_lines. Which file should be edited?", files)
    text = (ROOT / path).read_text()
    lines = text.split("\n")
    n = len(lines)
    # Narrow to the function(s) the failure points at, when we can tell.
    ranges = focus_ranges(ROOT / path, text, state["last_run"])
    # A big file only fits the context window if we can show just the failing part.
    if len(text) > MAX_PROMPT_FILE and not ranges:
        return {"path": path, "error": f"{path} is too large to edit in place "
                                        f"({len(text)} chars, limit {MAX_PROMPT_FILE}) and the "
                                        "check output does not say which function failed."}
    visible = sorted({i for s, e in ranges for i in range(s, e + 1)}) or list(range(1, n + 1))
    end_limit = {i: max(e for s, e in ranges if s <= i <= e) for i in visible} if ranges else {}
    numbered = "\n".join(f"{i}: {lines[i - 1]}" for i in visible)
    problem = f"\n\nCheck output (the problem to fix):\n{state['last_run']}" if state["last_run"] else ""
    # The retry has no memory of why the last edit was rejected, so say it explicitly.
    problem += f"\n\n{state['edit_feedback']}" if state["edit_feedback"] else ""
    # Fresh, small context: the whole conversation would not fit next to the file.
    where = "The failure is in this code" if ranges else "File"
    ctx = [{"role": "system", "content": EDITOR},
           {"role": "user", "content": f"Task: {task}{problem}\n\n{where} (`{path}`):\n{numbered}"}]
    start = ask_int(ctx, "start_line",
                    "Fix ONE problem only. Which line number starts the small block of code "
                    "that contains the problem? If the wrong line is inside an if/for/def, "
                    "start at that if/for/def line.", visible)
    ctx.append({"role": "assistant", "content": json.dumps({"start_line": start})})
    last = min(n, start + MAX_EDIT_SPAN - 1, end_limit.get(start, n))
    end = ask_int(ctx, "end_line",
                  f"Which line number ends that block? It must be {start} or later and the "
                  f"block must be small.", range(start, last + 1))
    prompt = (f"Task: {task}{problem}\n\n{where} (`{path}`):\n{numbered}\n\n"
              f"Rewrite lines {start} to {end} with the problem fixed. Reply with one fenced "
              f"code block containing only the new version of those lines, with the same "
              f"indentation and without line numbers.")
    reply = chat([{"role": "system", "content": WRITER}, {"role": "user", "content": prompt}])
    return {"path": path, "start_line": start, "end_line": end,
            "new": "\n".join(clean_replacement(reply))}


def run_tool(tool, a, task, state):
    if tool == "list_dir":
        return "\n".join(sorted(x.name + ("/" if x.is_dir() else "")
                                for x in safe_path(a["path"] or ".").iterdir()))
    if tool == "read_file":
        p = safe_path(a["path"])
        if not p.is_file():
            return "error: no such file. Existing files: " + ", ".join(list_files())
        return p.read_text()
    if tool == "write_file":
        p = safe_path(a["path"])
        if p.is_dir() or not p.name:
            return "error: path must be a file name like app.py, not a directory"
        existing = p.read_text() if p.exists() else ""
        feedback, text, err = state["last_run"], "", ""
        for _ in range(3):  # regenerate with the checker's error until it parses
            text = write_contents(task, a["path"], existing, feedback)
            err = syntax_error(p, text)
            if not err:
                break
            existing, feedback = text, err
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return f"wrote {a['path']}" + (f" but it still has an error: {err}" if err else "") \
            + after_edit(state)
    if tool == "edit_lines":
        if "error" in a:
            return f"error: {a['error']}"
        p = safe_path(a["path"])
        lines = p.read_text().split("\n")
        s, e = a["start_line"], a["end_line"]
        new_lines = reindent(a["new"].split("\n"), lines[s - 1]) if a["new"].strip() else []
        targeted = "\n".join(lines[s - 1:e])

        def reject(why):
            state["edit_feedback"] = (f"Your previous edit was rejected: you targeted lines "
                                      f"{s}-{e}:\n{targeted}\nbut {why} Choose different lines.")
            return f"error: edit not applied: {why}"

        if new_lines == lines[s - 1:e]:
            return reject("the new lines were identical to the old ones.")
        updated = "\n".join(lines[:s - 1] + new_lines + lines[e:])
        syn = syntax_error(p, updated)
        if syn:
            return reject(f"it would break the file ({syn}).")
        lost = defined_names(p, "\n".join(lines)) - defined_names(p, updated)
        if lost:
            return reject(f"it would delete {', '.join(sorted(lost))}.")
        p.write_text(updated)
        state["edit_feedback"] = ""
        state["edited"] = True
        return f"edited {a['path']} lines {s}-{e}" + after_edit(state)
    if tool == "run_command":
        cmd = re.sub(r"^\s*(run_command|command)\s*:\s*", "", a["command"]).strip()
        # Human approval gate: the model should not run arbitrary shell unattended.
        try:
            answer = input(f"\n  run `{cmd}`? [y/N] ").strip().lower()
        except EOFError:  # no terminal (CI, benchmark): treat as a denial
            answer = ""
        if answer != "y":
            return "user denied the command"
        r = subprocess.run(cmd, shell=True, cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        out = f"$ {cmd}\nexit {r.returncode}\n{r.stdout}{r.stderr}"[:MAX_OBS]
        if not state["check"]:
            state["last_run"] = out
            if r.returncode == 0:
                out += "\nThe command succeeded. If the task is complete, call done."
        return out
    return f"unknown tool: {tool}"


def short(args):
    return " ".join(str(v).replace("\n", "\\n")[:60] for k, v in args.items() if v != "")


# ---------- loop ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", help="command that must exit 0 for the task to count as done")
    ap.add_argument("-v", "--verbose", action="store_true", help="log each model call")
    ap.add_argument("task", nargs="+")
    ns = ap.parse_args()
    global VERBOSE
    VERBOSE = ns.verbose
    task = " ".join(ns.task)

    server = ensure_server()
    system = SYSTEM.format(check_rules=CHECK_RULES if ns.check else NO_CHECK_RULES)
    state = {"last_run": "", "check": ns.check, "check_ok": False,
             "edit_feedback": "", "edited": False}
    first_user = task
    try:
        if ns.check:
            # Run the check once up front so the model starts from the real failure.
            ok, out = run_check(ns.check)
            state["last_run"], state["check_ok"] = out, ok
            if ok:
                print("check already passes; nothing to do")
                return 0
            print("initial check FAILED:\n    " + out[:300].replace("\n", "\n    "))
            first_user = f"{task}\n\nThe check currently fails:\n{out}"
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": first_user}]
        seen = set()

        for step in range(1, MAX_STEPS + 1):
            trim_history(messages)
            tool, args = choose_action(messages, task, state)
            print(f"[{step}] {tool} {short(args)}")

            if tool == "done":
                if ns.check:
                    ok, out = run_check(ns.check)
                    if ok:
                        print("done; check passed")
                        return 0
                    obs = f"Not done: the check is failing.\n{out}"
                    state["last_run"] = out
                else:
                    print("done")
                    return 0
            else:
                key = (tool, json.dumps(args, sort_keys=True))
                if key in seen and tool in ("run_command", "read_file", "list_dir"):
                    obs = "You already did this exact action. Do something different."
                else:
                    try:
                        obs = run_tool(tool, args, task, state)
                    except Exception as e:
                        obs = f"error: {e}"
                if tool in ("write_file", "edit_lines") and not obs.startswith("error"):
                    seen.clear()  # file changed, so re-running/reading is legitimate again
                seen.add(key)

            obs = obs[:MAX_OBS]
            print("    ->", obs.replace("\n", "\n       ")[:400])
            if ns.check and state["check_ok"] and tool in ("write_file", "edit_lines") \
                    and not obs.startswith("error"):
                print(f"check passed after {step} step(s)")
                return 0
            record = {"tool": tool, **{k: str(v)[:150] for k, v in args.items()}}
            messages.append({"role": "assistant", "content": json.dumps(record)})
            messages.append({"role": "user", "content": f"Result:\n{obs}"})
        print("stopped: hit MAX_STEPS")
        return 1
    finally:
        if server:
            server.terminate()


if __name__ == "__main__":
    sys.exit(main())
