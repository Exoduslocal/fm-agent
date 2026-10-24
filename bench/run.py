#!/usr/bin/env python3
"""Benchmark runner for fm-agent.

    python3 bench/run.py --selftest             # validate tasks against reference solutions
    python3 bench/run.py -n 10                  # run everything, 10 trials per cell
    python3 bench/run.py -n 3 --arms python --tasks fizzbuzz,fix-stats
    python3 bench/run.py --report               # rebuild the tables from saved runs

Arms
    baseline  One shot, no harness: the task (plus the target file and the failing check
              output, for tasks that start with a file) goes to the model once, and the
              fenced code block it returns is written to the target file. No tools,
              no retries, no feedback.
    python    fm_agent.py  --check <check> "<prompt>"
    swift     swift/.build/release/fm-agent --check <check> "<prompt>"

Every trial runs in a fresh temp copy of the task's seed/ directory. Afterwards the
runner itself runs the task's `check` (what the agent sees) and `verify` (held-out tests
in hidden/, copied in only after the agent has finished). A trial passes only if the
runner's own run of the command exits 0, regardless of what the agent claimed.

Results are appended to <out>/runs.jsonl after every trial, so an interrupted run can be
continued with the same command: finished trials are skipped.
"""
import argparse
import json
import math
import os
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TASKS_DIR = HERE / "tasks"
PY_AGENT = REPO / "fm_agent.py"
SWIFT_BIN = REPO / "swift" / ".build" / "release" / "fm-agent"
PORT = 1976
ARMS = ["baseline", "python", "swift"]
ARM_LABEL = {"baseline": "Baseline (one shot)", "python": "Python harness", "swift": "Swift harness"}
AGENT_TIMEOUT = 180   # seconds per trial before the agent is killed (counts as a failure)
CHECK_TIMEOUT = 60
WRITER = ("You are an expert programmer. Reply with exactly one fenced code block "
          "containing the complete file, and nothing else.")


# ---------- tasks ----------

def load_tasks(names=None):
    tasks = {}
    for d in sorted(TASKS_DIR.iterdir()):
        if d.is_dir() and (d / "task.json").exists() and (not names or d.name in names):
            t = json.loads((d / "task.json").read_text())
            t["name"], t["dir"] = d.name, d
            tasks[d.name] = t
    missing = set(names or []) - set(tasks)
    if missing:
        sys.exit(f"unknown task(s): {', '.join(sorted(missing))}")
    return tasks


def sh(cmd, cwd, timeout=CHECK_TIMEOUT):
    """Run a shell command with no bytecode caching. Returns (exit_code, output)."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def evaluate(task, sandbox):
    """Run the visible check, then copy in hidden tests and run the verifier."""
    code, out = sh(task["check"], sandbox)
    check_ok = code == 0
    if task.get("verify"):
        hidden = task["dir"] / "hidden"
        if hidden.exists():
            shutil.copytree(hidden, sandbox, dirs_exist_ok=True)
        vcode, vout = sh(task["verify"], sandbox)
        return check_ok, vcode == 0, (vout if vcode else out)
    return check_ok, check_ok, out


# ---------- model server (python arm) ----------

class Server:
    """Owns `fm serve` so a hung or runaway request can't leak into the next trial."""

    def __init__(self):
        self.proc = None

    def healthy(self):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
            return True
        except Exception:
            return False

    def ensure(self):
        if self.proc and self.proc.poll() is None and self.healthy():
            return
        self.stop()
        if self.healthy():
            sys.exit(f"something else is already serving on port {PORT}; stop it first")
        # Loopback only: `fm serve` has no authentication.
        self.proc = subprocess.Popen(["fm", "serve", "--host", "127.0.0.1", "--port", str(PORT)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
        for _ in range(60):
            if self.healthy():
                return
            time.sleep(0.25)
        sys.exit("fm serve did not start")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait()
        self.proc = None


# ---------- arms ----------

def run_process(argv, cwd, timeout):
    """Run an agent in its own process group, merge output, kill the group on timeout.
    stdin is closed, so any run_command approval prompt is answered with a denial."""
    p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, False
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return 124, out or "", True


def fenced(text):
    m = re.search(r"```[\w+-]*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def arm_baseline(task, sandbox):
    target = sandbox / task["target"]
    prompt = task["prompt"]
    if target.exists():
        _, failing = sh(task["check"], sandbox)
        prompt += (f"\n\nCurrent contents of {task['target']}:\n{target.read_text()}"
                   f"\n\nThe check currently fails:\n{failing[:1200]}")
    prompt += f"\n\nWrite the complete file `{task['target']}`."
    r = subprocess.run(["fm", "respond", "--no-stream", "-i", WRITER, prompt],
                       capture_output=True, text=True, timeout=AGENT_TIMEOUT)
    if r.returncode != 0:
        return r.returncode, (r.stdout + r.stderr), False
    target.write_text(fenced(r.stdout))
    return 0, "[1] write_file (one shot)", False


def arm_python(task, sandbox):
    return run_process([sys.executable, str(PY_AGENT), "--check", task["check"], task["prompt"]],
                       sandbox, AGENT_TIMEOUT)


def arm_swift(task, sandbox):
    return run_process([str(SWIFT_BIN), "--check", task["check"], task["prompt"]],
                       sandbox, AGENT_TIMEOUT)


ARM_FN = {"baseline": arm_baseline, "python": arm_python, "swift": arm_swift}


def count_tool_calls(arm, out):
    if arm == "baseline":
        return 1
    if arm == "python":
        return len(re.findall(r"^\[\d+\] ", out, re.M))
    return len(re.findall(r"^  \[(?:list_dir|read_file|write_file|edit_lines|run_command)\]", out, re.M))


# ---------- one trial ----------

def run_trial(arm, task, i, server, logs):
    sandbox = Path(tempfile.mkdtemp(prefix=f"fmbench-{task['name']}-"))
    try:
        shutil.copytree(task["dir"] / "seed", sandbox, dirs_exist_ok=True)
        if arm == "python":
            server.ensure()
        t0 = time.time()
        try:
            code, out, timed_out = ARM_FN[arm](task, sandbox)
        except subprocess.TimeoutExpired:
            code, out, timed_out = 124, "timed out", True
        seconds = time.time() - t0
        if timed_out and arm == "python":
            server.stop()  # a killed request keeps generating server-side; start fresh
        check_ok, hidden_ok, detail = evaluate(task, sandbox)
        (logs / f"{arm}-{task['name']}-{i}.log").write_text(
            f"exit={code} timed_out={timed_out} seconds={seconds:.1f}\n\n{out}\n\n--- final check ---\n{detail}\n")
        return {"arm": arm, "task": task["name"], "trial": i, "check_pass": check_ok,
                "hidden_pass": hidden_ok, "seconds": round(seconds, 1),
                "tool_calls": count_tool_calls(arm, out), "exit_code": code,
                "timed_out": timed_out}
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


# ---------- selftest ----------

def selftest(tasks):
    """Each task must FAIL its check as seeded, and PASS check+verify with the reference
    solution. Otherwise a broken task would be scored as a model failure."""
    bad = 0
    for t in tasks.values():
        sb = Path(tempfile.mkdtemp(prefix="fmbench-selftest-"))
        try:
            shutil.copytree(t["dir"] / "seed", sb, dirs_exist_ok=True)
            seeded_ok, _, _ = evaluate(t, sb)
            shutil.copytree(t["dir"] / "solution", sb, dirs_exist_ok=True)
            sol_check, sol_hidden, detail = evaluate(t, sb)
            ok = (not seeded_ok) and sol_check and sol_hidden
            print(f"{'ok  ' if ok else 'FAIL'} {t['name']:16s} seed fails check: {not seeded_ok}"
                  f" | solution passes check: {sol_check} hidden: {sol_hidden}")
            if not ok:
                bad += 1
                print("     ", detail[:200].replace("\n", " | "))
        finally:
            shutil.rmtree(sb, ignore_errors=True)
    return bad == 0


# ---------- statistics and report ----------

def wilson(k, n, z=1.96):
    """95% Wilson score interval for a proportion (sane for small n and for 0%/100%)."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(x):
    return f"{round(100 * x)}%"


def cell(rows, key):
    n = len(rows)
    if n == 0:
        return "-"
    k = sum(1 for r in rows if r[key])
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({pct(k / n)}) [{pct(lo)}-{pct(hi)}]"


def env_info():
    def run(*a):
        try:
            return subprocess.run(a, capture_output=True, text=True, timeout=10).stdout.strip()
        except Exception:
            return "unknown"
    return {
        "date": time.strftime("%Y-%m-%d"),
        "chip": run("sysctl", "-n", "machdep.cpu.brand_string"),
        "memory_gb": int(run("sysctl", "-n", "hw.memsize") or 0) // 1073741824,
        "macos": run("sw_vers", "-productVersion"),
        "python": platform.python_version(),
        "swift": (run("swift", "--version").splitlines() or ["unknown"])[0],
    }


def report(runs, tasks, env):
    arms = [a for a in ARMS if any(r["arm"] == a for r in runs)]
    names = [t for t in tasks if any(r["task"] == t for r in runs)]
    out = []
    n_per = sorted({sum(1 for r in runs if r["arm"] == a and r["task"] == names[0]) for a in arms}) if names else []
    out.append(f"Trials per task per arm: {', '.join(map(str, n_per))}. "
               "Cells show passes/trials (rate) [95% Wilson interval].\n")

    for key, title in [("hidden_pass", "Held-out tests (headline: the agent never sees these)"),
                       ("check_pass", "Visible check (the tests the agent is given and optimizes against)")]:
        out.append(f"### {title}\n")
        out.append("| Task | " + " | ".join(ARM_LABEL[a] for a in arms) + " |")
        out.append("|---|" + "---|" * len(arms))
        for t in names:
            out.append(f"| {t} ({tasks[t].get('split', '?')}) | " + " | ".join(
                cell([r for r in runs if r["arm"] == a and r["task"] == t], key) for a in arms) + " |")
        for label, split in [("Dev tasks (harness was tuned on these)", "dev"),
                             ("Fresh tasks (written after tuning, never used to tune)", "fresh"),
                             ("Scale task (file too big for a one-shot rewrite)", "scale")]:
            members = {t for t in names if tasks[t].get("split") == split}
            if members:
                out.append(f"| {label} | " + " | ".join(
                    cell([r for r in runs if r["arm"] == a and r["task"] in members], key)
                    for a in arms) + " |")
        small = {t for t in names if tasks[t].get("split") != "scale"}
        if small and len(small) < len(names):
            out.append("| All small tasks (everything except scale) | " + " | ".join(
                cell([r for r in runs if r["arm"] == a and r["task"] in small], key)
                for a in arms) + " |")
        out.append("| **All tasks** | " + " | ".join(
            "**" + cell([r for r in runs if r["arm"] == a], key) + "**" for a in arms) + " |\n")

    out.append("### Cost and failure modes\n")
    out.append("| Arm | Median time / trial | Median tool calls | Timeouts | Pass visible, fail hidden |")
    out.append("|---|---|---|---|---|")
    for a in arms:
        rs = [r for r in runs if r["arm"] == a]
        if not rs:
            continue
        overfit = sum(1 for r in rs if r["check_pass"] and not r["hidden_pass"])
        out.append(f"| {ARM_LABEL[a]} | {statistics.median(r['seconds'] for r in rs):.0f}s "
                   f"| {statistics.median(r['tool_calls'] for r in rs):.0f} "
                   f"| {sum(1 for r in rs if r['timed_out'])}/{len(rs)} | {overfit}/{len(rs)} |")
    out.append("")
    out.append(f"Environment: {env.get('chip')}, {env.get('memory_gb')} GB, macOS {env.get('macos')}, "
               f"Python {env.get('python')}, {env.get('swift')}. Run date: {env.get('date')}.")
    return "\n".join(out)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--trials", type=int, default=10, help="trials per task per arm")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--tasks", default="", help="comma-separated task names (default: all)")
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--selftest", action="store_true", help="validate tasks, run no model")
    ap.add_argument("--report", action="store_true", help="rebuild the report from saved runs")
    ns = ap.parse_args()

    tasks = load_tasks([t for t in ns.tasks.split(",") if t])
    if ns.selftest:
        sys.exit(0 if selftest(tasks) else 1)

    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    runs_file = out / "runs.jsonl"
    runs = [json.loads(l) for l in runs_file.read_text().splitlines()] if runs_file.exists() else []

    if ns.report:
        env = json.loads((out / "env.json").read_text()) if (out / "env.json").exists() else env_info()
        text = report(runs, load_tasks(), env)
        (out / "REPORT.md").write_text(text + "\n")
        print(text)
        return

    arms = [a for a in ns.arms.split(",") if a]
    for a in arms:
        if a not in ARMS:
            sys.exit(f"unknown arm {a}; choose from {ARMS}")
    if "swift" in arms and not SWIFT_BIN.exists():
        sys.exit(f"{SWIFT_BIN} not found. Build it: (cd swift && swift build -c release)")
    if not selftest(tasks):
        sys.exit("task self-test failed; fix the tasks before benchmarking")
    (out / "env.json").write_text(json.dumps(env_info(), indent=2))

    done = {(r["arm"], r["task"], r["trial"]) for r in runs}
    server = Server()
    total = len(arms) * len(tasks) * ns.trials
    count = len(done)
    try:
        # Interleave arms and tasks inside each trial index, so a partial run is balanced
        # and slow drift (thermals, background load) hits every arm equally.
        for i in range(ns.trials):
            for t in tasks.values():
                for a in arms:
                    if (a, t["name"], i) in done:
                        continue
                    r = run_trial(a, t, i, server, out / "logs")
                    runs.append(r)
                    with runs_file.open("a") as f:
                        f.write(json.dumps(r) + "\n")
                    count += 1
                    print(f"[{count}/{total}] {a:8s} {t['name']:14s} #{i}  "
                          f"hidden={'PASS' if r['hidden_pass'] else 'fail'}  "
                          f"{r['seconds']:5.1f}s  calls={r['tool_calls']}"
                          f"{'  TIMEOUT' if r['timed_out'] else ''}", flush=True)
    finally:
        server.stop()

    text = report(runs, load_tasks(), json.loads((out / "env.json").read_text()))
    (out / "REPORT.md").write_text(text + "\n")
    print("\n" + text)


if __name__ == "__main__":
    main()
