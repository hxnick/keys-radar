#!/usr/bin/env python3
"""Operator-side gate for single, explicitly authorized Symphony runs."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
TASKS = tuple(f"P0-{number:02d}" for number in range(1, 6))
SMOKE_TASK = "S0-SMOKE-01"
SMOKE_LABEL = "radar:s0-smoke"
SMOKE_FILES = (
    "AGENTS.md", "docs/PROJECT_BRIEF.md", "docs/ARCHITECTURE.md",
    "docs/ROADMAP.md", "docs/ACCEPTANCE_CRITERIA.md", f"tasks/{SMOKE_TASK}.md",
)
PHASES = {"backlog", "todo", "in-progress", "blocked", "human-review", "rework"}
RUN_PHASES = {"todo", "in-progress", "rework"}
START_PHASES = {"todo", "rework"}
RUN_LIMIT = 30 * 60
TOKEN_ENV = "KEYS_RADAR_GITHUB_TOKEN"
SAMPLE_REPO = "owner/keys-radar"


class GateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temp.replace(path)


def load_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def workflow(repo, smoke=False):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo), "Expected owner/repo.")
    require(repo.split("/")[1] not in (".", ".."), "Invalid GitHub repository name.")
    require(repo.lower() != SAMPLE_REPO, "Choose the authorized repository.")
    _, header, prompt = (ROOT / "WORKFLOW.md").read_text().split("---\n", 2)
    config = json.loads(header)
    tracker = config["tracker"]
    require(tracker == {
        "kind": "github", "provider": {"repo": SAMPLE_REPO, "token": f"${TOKEN_ENV}"},
        "required_labels": ["radar:run"], "active_states": ["open"], "terminal_states": [],
    }, "Unexpected workflow tracker profile.")
    require(config["agent"]["max_concurrent_agents"] == 1, "Concurrent agent limit must be one.")
    require(config["workspace"]["root"] == "$KEYS_RADAR_WORKSPACE_ROOT", "Unexpected workspace root.")
    require("{{ issue.identifier }}" in prompt and len(re.findall(r"{{", prompt)) == 1, "Unexpected prompt variables.")
    for name in ("after_create", "before_run", "after_run", "before_remove"):
        subprocess.run(["/bin/bash", "-n", "-c", config["hooks"][name]], check=True)
    tracker["provider"]["repo"] = repo
    if smoke:
        tracker["required_labels"].append(SMOKE_LABEL)
        config["agent"]["max_turns"] = 1
        prompt = (
            "\n本次联调对应 {{ issue.identifier }}。先读取 AGENTS.md、.radar-task.json 和绑定的"
            " tasks/S0-SMOKE-01.md。只执行该文件的联调任务，保留 pytest 实际输出和交付证据。"
            "使用工作区控制文件给出的 pytest 路径。停在人工审核，不修改 GitHub 或接续开发。\n"
        )
    return f"---\n{json.dumps(config, ensure_ascii=False, indent=2)}\n---\n{prompt}"


def state_root():
    path = ROOT / ".symphony-state"
    require(not path.is_symlink(), "State root cannot be a symlink.")
    path.mkdir(mode=0o700, exist_ok=True)
    require(path.stat().st_mode & 0o077 == 0, "State directory must be private (0700).")
    return path


@contextmanager
def operator_lock(state):
    with (state / "operator.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise GateError("Another operator command or Symphony run is active.") from exc
        yield


def acceptance_path(state, task):
    return state / f"accepted-{task}.json"


def accept_s0(state, repo, report):
    workflow(repo)
    receipt = acceptance_path(state, "S0")
    require(not receipt.exists(), "S0 is already accepted for a repository.")
    report_text = report.read_bytes()
    require(bool(report_text.strip()), "S0 acceptance report is empty.")
    write_json(receipt, {"repo": repo.lower(), "report": str(report.resolve()),
                         "sha256": hashlib.sha256(report_text).hexdigest(), "accepted_at": now()})


def git(cwd, *arguments):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(cwd), *arguments],
        check=True, text=True, stdout=subprocess.PIPE, timeout=35, env=env,
    )
    return result.stdout.strip()


def clean_baseline():
    require(git(ROOT, "rev-parse", "--show-toplevel") == str(ROOT), "A dedicated local Git repository is required.")
    require(not git(ROOT, "status", "--porcelain"), "Review and commit the local project baseline first.")
    return git(ROOT, "rev-parse", "--verify", "HEAD")


def verify_chain(state, repo, task):
    require(task in TASKS, "Only P0-01 to P0-05 are enabled.")
    require(acceptance_path(state, "S0").is_file(), "Human acceptance of S0 is required.")
    require(load_json(acceptance_path(state, "S0"))["repo"] == repo.lower(), "Repository differs from S0 approval.")
    require(not acceptance_path(state, task).exists(), "This task is already accepted.")
    baseline = clean_baseline()
    for predecessor in TASKS[:TASKS.index(task)]:
        receipt = acceptance_path(state, predecessor)
        require(receipt.is_file(), f"Human acceptance of {predecessor} is required.")
        integrated = load_json(receipt)["integrated_commit"]
        git(ROOT, "merge-base", "--is-ancestor", integrated, baseline)
    return baseline


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_issue(repo, issue):
    token = os.environ.get(TOKEN_ENV)
    require(token, f"Set {TOKEN_ENV} locally with Issues read permission for the approved repository.")
    request = Request(
        f"https://api.github.com/repos/{repo}/issues/{issue}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=8) as response:
            return json.load(response)
    except (URLError, ValueError, TimeoutError) as exc:
        raise GateError(f"GitHub Issue check failed ({type(exc).__name__}).") from exc


def issue_allowed(payload, issue, phases, smoke=False):
    if (
        not isinstance(payload, dict) or payload.get("number") != issue
        or payload.get("state") != "open" or "pull_request" in payload
    ):
        return False
    labels = payload.get("labels")
    if not isinstance(labels, list):
        return False
    names = {
        label["name"].strip().lower()
        for label in labels if isinstance(label, dict) and isinstance(label.get("name"), str)
    }
    states = names & {f"radar:{phase}" for phase in PHASES}
    return (
        ("radar:run" in names and ((SMOKE_LABEL in names) == smoke))
        and len(states) == 1 and states <= {f"radar:{phase}" for phase in phases}
    )


def local_run(state, name):
    require(re.fullmatch(r"(?:P0-0[1-5]|S0-SMOKE-01)-[a-z0-9_]+", name), "Invalid local run ID.")
    run = state / "runs" / name
    require(run.is_dir() and not run.is_symlink(), "Local run was not found.")
    return run


def workspace_path(run, issue):
    retained = run / "retained"
    return retained if retained.is_dir() else run / "workspaces" / f"GH-{issue}"


def validate_result(workspace, manifest):
    task = manifest["task"]
    folder = workspace / "reports"
    require(folder.is_dir() and not folder.is_symlink(), "Reports must be a local workspace directory.")
    output = folder / f"{task}-result.json"
    require(output.is_file() and not output.is_symlink(), "Structured result is missing.")
    result = load_json(output)
    require(result.get("task") == task and result.get("issue") == manifest["issue"], "Run evidence identity differs.")
    require(result.get("result") == "passed", "Task report still has a failure or blocker.")
    tests = result.get("tests")
    require(isinstance(tests, list) and tests and all(
        isinstance(test, dict) and isinstance(test.get("command"), str) and test["command"].strip()
        and type(test.get("exit_code")) is int and test["exit_code"] == 0 for test in tests
    ), "At least one successful test and all exit codes must be recorded.")
    report = folder / f"{task}-delivery.md"
    require(report.is_file() and not report.is_symlink() and bool(report.read_bytes().strip()),
            "Delivery report is missing or empty.")
    if task == SMOKE_TASK:
        for directory, filenames in (
            (workspace / "smoke_test", ("hello.py", "test_hello.py")),
            (folder, (f"{SMOKE_TASK}-pytest.txt",)),
        ):
            require(directory.is_dir() and not directory.is_symlink(), "Expected a local evidence directory.")
            for filename in filenames:
                artifact = directory / filename
                require(artifact.is_file() and not artifact.is_symlink() and artifact.stat().st_size > 0,
                        f"Missing smoke artifact: {filename}")
    return report


def verify_retained(state, name):
    run = local_run(state, name)
    manifest = load_json(run / "run.json")
    require((run / "started").exists(), "No worker attempt was authorized in this run.")
    require((run / "stop.json").is_file(), "The supervisor has not finalized this run.")
    return manifest, validate_result(workspace_path(run, manifest["issue"]), manifest)


def accept_task(state, name, report):
    manifest, delivery = verify_retained(state, name)
    require(manifest["task"] != SMOKE_TASK, "Smoke human review does not accept S0 or a P0 baseline.")
    baseline = verify_chain(state, manifest["repo"], manifest["task"])
    git(ROOT, "merge-base", "--is-ancestor", manifest["baseline"], baseline)
    evidence = report.read_bytes()
    require(bool(evidence.strip()), "Human verification evidence is empty.")
    write_json(acceptance_path(state, manifest["task"]), {
        "issue": manifest["issue"], "run": name, "delivery": str(delivery),
        "human_evidence": str(report.resolve()), "sha256": hashlib.sha256(evidence).hexdigest(),
        "integrated_commit": baseline, "accepted_at": now(),
    })


def run_hook(action, run):
    manifest = load_json(run / "run.json")
    work = Path.cwd()
    require(work == run / "workspaces" / f"GH-{manifest['issue']}", "Issue was not authorized for this run.")
    smoke = manifest["task"] == SMOKE_TASK
    if action == "prepare":
        if smoke:
            for filepath in SMOKE_FILES:
                destination = work / filepath
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / filepath, destination)
        elif manifest["resume"]:
            old = Path(manifest["resume"])
            shutil.copytree(old, work, dirs_exist_ok=True, symlinks=True)
        else:
            git(work, "clone", "--no-local", "--no-checkout", "--", str(ROOT), ".")
            # Remove the local source reference before opening the workspace to Codex.
            git(work, "remote", "remove", "origin")
            git(work, "switch", "-c", f"radar/gh-{manifest['issue']}", manifest["baseline"])
        return
    if action == "before-run":
        if smoke:
            issue_number = manifest["issue"]
            require(issue_allowed(read_issue(manifest["repo"], issue_number), issue_number, RUN_PHASES, smoke=True),
                    "The smoke issue no longer authorizes execution.")
        else:
            require(git(work, "branch", "--show-current") == f"radar/gh-{manifest['issue']}", "Unexpected branch.")
            git(work, "merge-base", "--is-ancestor", manifest["baseline"], "HEAD")
        with (run / "started").open("x", encoding="utf-8") as flag:
            flag.write(now())
        task = manifest["task"]
        require(not (work / "reports").is_symlink(), "Reports may not be a symlink.")
        for suffix in ("delivery.md", "result.json"):
            evidence = work / "reports" / f"{task}-{suffix}"
            if evidence.exists() or evidence.is_symlink():
                evidence.rename(run / f"previous-{suffix}")
        binding = {
            "task": manifest["task"], "issue": manifest["issue"], "task_file": f"tasks/{manifest['task']}.md",
        }
        if smoke:
            binding["pytest"] = manifest["pytest"]
        write_json(work / ".radar-task.json", binding)
        return
    if action == "after-run":
        require((run / "started").exists(), "No authorized worker attempt.")
        (run / "ended").touch()
        return
    require(action == "preserve", "Unknown hook.")
    # Same-volume rename keeps untracked files, Git index, history and local reports intact.
    work.rename(run / "retained")


def terminate(child):
    for sig, timeout in ((signal.SIGTERM, 8), (signal.SIGKILL, 4)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if sig == signal.SIGTERM:
            # Descendants in the group can survive a parent that exits early.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return
    raise GateError("Process group did not stop within the shutdown timeout.")


def supervise(run, manifest, binary):
    env = os.environ | {
        "KEYS_RADAR_PYTHON": sys.executable,
        "KEYS_RADAR_HOOK_SCRIPT": str(Path(__file__).resolve()),
        "KEYS_RADAR_RUN_DIR": str(run),
        "KEYS_RADAR_WORKSPACE_ROOT": str(run / "workspaces"),
    }
    smoke = manifest["task"] == SMOKE_TASK
    deadline = time.monotonic() + (min(RUN_LIMIT, 300) if smoke else RUN_LIMIT)
    recheck = time.monotonic() + 15
    with (run / "launcher.log").open("ab") as log:
        child = subprocess.Popen([str(binary), "--logs-root", str(run / "logs"), str(run / "WORKFLOW.md")],
                                 cwd=run, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while time.monotonic() < deadline:
                if (run / "halt").exists():
                    raise GateError("Session stopped by a workflow hook; review launcher.log.")
                if (run / "ended").exists():
                    return "attempt_ended"
                if child.poll() is not None:
                    raise GateError(f"Symphony exited with code {child.returncode}; review launcher.log.")
                if time.monotonic() >= recheck:
                    if not issue_allowed(read_issue(manifest["repo"], manifest["issue"]), manifest["issue"],
                                         RUN_PHASES, smoke=smoke):
                        return "paused_by_tracker"
                    recheck = time.monotonic() + 15
                time.sleep(0.25)
            return "deadline"
        finally:
            terminate(child)


def pause_on_terminate(_signal, _frame):
    raise KeyboardInterrupt


def start_run(state, args):
    smoke = args.task == SMOKE_TASK
    config = workflow(args.repo, smoke=smoke)
    baseline = None if smoke else verify_chain(state, args.repo, args.task)
    binary = args.symphony.expanduser().resolve(strict=True)
    require(binary.is_file() and os.access(binary, os.X_OK), "Symphony binary must be executable.")
    require(args.issue > 0, "Issue number must be positive.")
    issue = read_issue(args.repo, args.issue)
    require(issue_allowed(issue, args.issue, START_PHASES, smoke=smoke),
            "Issue must be open, runnable and in Todo or Rework for the selected task profile.")
    pytest = ROOT / ".venv" / "bin" / "pytest"
    if smoke:
        require(os.access(pytest, os.X_OK), "The project pytest executable is required for smoke testing.")
    previous_workspace = ""
    if args.resume:
        previous = local_run(state, args.resume)
        prior = load_json(previous / "run.json")
        require((prior["repo"], prior["task"], prior["issue"], prior["baseline"]) ==
                (args.repo.lower(), args.task, args.issue, baseline), "Resume must use the original approved baseline.")
        previous_workspace = str(workspace_path(previous, args.issue).resolve(strict=True))

    runs = state / "runs"
    runs.mkdir(exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f"{args.task}-", dir=runs))
    (run / "workspaces").mkdir()
    (run / "logs").mkdir()
    manifest = {"repo": args.repo.lower(), "task": args.task, "issue": args.issue, "baseline": baseline,
                "resume": previous_workspace, "authorized_at": now()}
    if smoke:
        manifest["pytest"] = str(pytest)
    write_json(run / "run.json", manifest)
    (run / "WORKFLOW.md").write_text(config)
    print(f"Local run: {run.name}", flush=True)
    result = "blocked"
    previous_handler = signal.signal(signal.SIGTERM, pause_on_terminate)
    try:
        result = supervise(run, manifest, binary)
        print(f"Stopped: {result}. Review workspace and logs in {run}.")
    except KeyboardInterrupt:
        result = "paused_by_operator"
        print(f"Paused. Review workspace and logs in {run}.")
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        write_json(run / "stop.json", {"result": result, "time": now()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    s0 = commands.add_parser("accept-s0")
    s0.add_argument("--repo", required=True)
    s0.add_argument("--evidence", type=Path, required=True)
    start = commands.add_parser("run")
    start.add_argument("--repo", required=True)
    start.add_argument("--task", choices=TASKS, required=True)
    start.add_argument("--issue", type=int, required=True)
    start.add_argument("--symphony", type=Path, required=True)
    start.add_argument("--resume")
    smoke = commands.add_parser("smoke-run")
    smoke.add_argument("--repo", required=True)
    smoke.add_argument("--issue", type=int, required=True)
    smoke.add_argument("--symphony", type=Path, required=True)
    smoke.set_defaults(task=SMOKE_TASK, resume=None)
    review = commands.add_parser("review")
    review.add_argument("run_id")
    accept = commands.add_parser("accept")
    accept.add_argument("run_id")
    accept.add_argument("--evidence", type=Path, required=True)
    hook = commands.add_parser("hook")
    hook.add_argument("action", choices=("prepare", "before-run", "after-run", "preserve"))
    args = parser.parse_args()
    run = None
    try:
        if args.command == "verify":
            workflow("local-validation/keys-radar")
            workflow("local-validation/keys-radar", smoke=True)
            print("Workflow front matter, profile, template variable and hook shell syntax are valid.")
            return 0
        if args.command == "hook":
            run = Path(os.environ["KEYS_RADAR_RUN_DIR"]).resolve(strict=True)
            run_hook(args.action, run)
            return 0
        state = state_root()
        with operator_lock(state):
            if args.command == "accept-s0":
                accept_s0(state, args.repo, args.evidence)
            elif args.command in ("run", "smoke-run"):
                start_run(state, args)
            elif args.command == "review":
                _, delivery = verify_retained(state, args.run_id)
                print(f"Evidence format verified. Human review required: {delivery}")
            elif args.command == "accept":
                accept_task(state, args.run_id, args.evidence)
    except (GateError, KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        if run is not None:
            (run / "halt").touch()
        print(f"Blocked: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
