"""Local simulations for the S0 launcher. No calls to GitHub or Codex turns."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import textwrap

import pytest

from scripts import symphony_s0 as s0


def issue(number=42, phase="todo", runnable=True, state="open", **overrides):
    tags = [f"radar:{phase}"] + (["radar:run"] if runnable else [])
    return dict(number=number, state=state, labels=[{"name": tag} for tag in tags]) | overrides


@pytest.mark.parametrize(("phase", "eligible"), [
    ("backlog", False), ("todo", True), ("in-progress", False), ("blocked", False),
    ("human-review", False), ("rework", True),
])
def test_start_phase_filter(phase, eligible):
    assert s0.issue_allowed(issue(phase=phase), 42, s0.START_PHASES) is eligible


def test_filter_checks_identity_marker_and_conflicting_states():
    assert not s0.issue_allowed(issue(number=24), 42, s0.START_PHASES)
    assert not s0.issue_allowed(issue(runnable=False), 42, s0.START_PHASES)
    assert not s0.issue_allowed(issue(state="closed"), 42, s0.START_PHASES)
    assert not s0.issue_allowed(issue(pull_request={}), 42, s0.START_PHASES)
    conflicting = issue()
    conflicting["labels"].append({"name": "radar:blocked"})
    assert not s0.issue_allowed(conflicting, 42, s0.START_PHASES)
    assert s0.issue_allowed(issue(phase="in-progress"), 42, s0.RUN_PHASES)


def test_workflow_renders_real_config_without_secrets():
    content = s0.workflow("simulated-owner/radar")
    _, header, _ = content.split("---\n", 2)
    config = json.loads(header)
    assert config["tracker"]["provider"]["repo"] == "simulated-owner/radar"
    assert config["tracker"]["provider"]["token"] == "$KEYS_RADAR_GITHUB_TOKEN"
    assert config["tracker"]["terminal_states"] == []
    assert config["agent"]["max_concurrent_agents"] == 1
    with pytest.raises(s0.GateError):
        s0.workflow("owner/keys-radar")


@pytest.fixture
def project(tmp_path, monkeypatch):
    original = s0.ROOT
    root = tmp_path.resolve() / "project"
    root.mkdir()
    (root / "scripts").mkdir()
    shutil.copy2(original / "WORKFLOW.md", root)
    shutil.copy2(original / "scripts/symphony_s0.py", root / "scripts")
    (root / ".gitignore").write_text("/.symphony-state/\n")
    (root / "example.txt").write_text("模拟基线\n")
    s0.git(root, "init", "-b", "main")
    s0.git(root, "add", ".")
    s0.git(root, "-c", "user.name=S0 Simulation", "-c", "user.email=s0@example.invalid",
           "-c", "commit.gpgsign=false", "commit", "-m", "simulated baseline")
    monkeypatch.setattr(s0, "ROOT", root)
    monkeypatch.setattr(s0, "__file__", str(root / "scripts/symphony_s0.py"))
    return root, s0.state_root()


def test_chain_needs_human_approval_and_accepted_predecessor(project, tmp_path):
    root, state = project
    report = tmp_path / "simulated-review.md"
    report.write_text("仅用于模拟的人工审批证据。\n")
    repo = "simulated-owner/radar"
    with pytest.raises(s0.GateError, match="acceptance of S0"):
        s0.verify_chain(state, repo, "P0-01")
    with pytest.raises(s0.GateError, match="Only P0"):
        s0.verify_chain(state, repo, "P1-01")
    s0.accept_s0(state, repo, report)
    assert s0.verify_chain(state, repo, "P0-01") == s0.clean_baseline()
    with pytest.raises(s0.GateError, match="Repository differs"):
        s0.verify_chain(state, "different/radar", "P0-01")
    with pytest.raises(s0.GateError, match="acceptance of P0-01"):
        s0.verify_chain(state, repo, "P0-02")
    s0.write_json(s0.acceptance_path(state, "P0-01"), {"integrated_commit": "not-a-commit"})
    with pytest.raises(s0.subprocess.CalledProcessError):
        s0.verify_chain(state, repo, "P0-02")


def test_operator_lock_rejects_second_invocation(project):
    _, state = project
    with s0.operator_lock(state), pytest.raises(s0.GateError, match="Another operator"):
        with s0.operator_lock(state):
            pass


def run_directory(state, baseline):
    run = state / "runs" / "P0-01-simulation"
    workspace = run / "workspaces" / "GH-42"
    workspace.mkdir(parents=True)
    data = {"issue": 42, "task": "P0-01", "repo": "simulated-owner/radar",
            "baseline": baseline, "resume": ""}
    s0.write_json(run / "run.json", data)
    return run, workspace, data


def test_hooks_isolate_limit_attempts_and_archive_untracked_work(project, monkeypatch):
    root, state = project
    run, workspace, data = run_directory(state, s0.clean_baseline())
    other = workspace.with_name("GH-99")
    other.mkdir()
    monkeypatch.chdir(other)
    with pytest.raises(s0.GateError, match="not authorized"):
        s0.run_hook("prepare", run)
    monkeypatch.chdir(workspace)
    s0.run_hook("prepare", run)
    s0.run_hook("before-run", run)
    assert s0.load_json(workspace / ".radar-task.json")["task_file"] == "tasks/P0-01.md"
    assert s0.git(workspace, "remote") == ""
    with pytest.raises(FileExistsError):
        s0.run_hook("before-run", run)
    (workspace / "example.txt").write_text("模拟已跟踪改动\n")
    (workspace / "untracked.txt").write_text("模拟未跟踪成果\n")
    s0.run_hook("after-run", run)
    assert (run / "ended").exists()
    s0.run_hook("preserve", run)
    monkeypatch.chdir(root)
    assert not workspace.exists()
    stored = s0.workspace_path(run, data["issue"])
    assert (stored / "untracked.txt").read_text() == "模拟未跟踪成果\n"
    assert (stored / "example.txt").read_text() == "模拟已跟踪改动\n"
    assert (root / "example.txt").read_text() == "模拟基线\n"


@pytest.mark.parametrize("code", [1, 0])
def test_review_requires_successful_record_and_human_acceptance(project, tmp_path, code):
    _, state = project
    run, workspace, data = run_directory(state, s0.clean_baseline())
    (run / "started").touch()
    s0.write_json(run / "stop.json", {"result": "attempt_ended"})
    folder = workspace / "reports"
    folder.mkdir()
    (folder / "P0-01-delivery.md").write_text("模拟交付")
    s0.write_json(folder / "P0-01-result.json", {
        "task": "P0-01", "issue": 42, "result": "passed",
        "tests": [{"command": "simulated test", "exit_code": code}],
    })
    if code:
        with pytest.raises(s0.GateError, match="exit codes"):
            s0.verify_retained(state, run.name)
        return
    _, report = s0.verify_retained(state, run.name)
    assert report.name == "P0-01-delivery.md"
    assert not s0.acceptance_path(state, "P0-01").exists()
    human = tmp_path / "human.md"
    human.write_text("模拟人工复核证据")
    s0.accept_s0(state, data["repo"], human)
    s0.accept_task(state, run.name, human)
    assert s0.verify_chain(state, data["repo"], "P0-02") == data["baseline"]


def test_supervised_simulation_stops_foreground_and_keeps_evidence(project, monkeypatch, tmp_path):
    root, state = project
    fake = tmp_path / "symphony-simulator"
    fake.write_text(f"#!{sys.executable}\n" + textwrap.dedent("""
        import json
        import os
        from pathlib import Path
        import subprocess
        import sys
        import time

        # Simulated Symphony lifecycle: parse the emitted workflow and run its hooks.
        assert sys.argv[1] == "--logs-root"
        _, header, _ = Path(sys.argv[3]).read_text().split("---\\n", 2)
        config = json.loads(header)
        work = Path(os.environ["KEYS_RADAR_WORKSPACE_ROOT"]) / "GH-42"
        work.mkdir()
        for name in ("after_create", "before_run"):
            subprocess.run(["/bin/bash", "-c", config["hooks"][name]], cwd=work, check=True)
        assert json.loads((work / ".radar-task.json").read_text())["task"] == "P0-01"
        (work / "simulation.txt").write_text("local simulation")
        subprocess.run(["/bin/bash", "-c", config["hooks"]["after_run"]], cwd=work, check=True)
        time.sleep(30)
    """).lstrip())
    fake.chmod(0o700)
    evidence = tmp_path / "simulated-evidence.md"
    evidence.write_text("模拟 S0 验收")
    s0.accept_s0(state, "simulated-owner/radar", evidence)
    monkeypatch.setattr(s0, "read_issue", lambda repo, number: issue(number=number))
    s0.start_run(state, argparse.Namespace(
        repo="simulated-owner/radar", task="P0-01", issue=42, symphony=fake, resume=None,
    ))
    [run] = list((state / "runs").iterdir())
    assert s0.load_json(run / "stop.json")["result"] == "attempt_ended"
    assert (s0.workspace_path(run, 42) / "simulation.txt").is_file()
    assert not (root / "simulation.txt").exists()


def test_rework_retains_older_evidence_and_starts_fresh(project, monkeypatch):
    root, state = project
    run, workspace, manifest = run_directory(state, s0.clean_baseline())
    monkeypatch.chdir(workspace)
    s0.run_hook("prepare", run)
    s0.run_hook("before-run", run)
    (workspace / "reports").mkdir()
    (workspace / "reports/P0-01-result.json").write_text("{}")
    (workspace / "untracked.txt").write_text("模拟返工前文件")

    retry = run.with_name("P0-01-rework")
    checkout = retry / "workspaces" / "GH-42"
    checkout.mkdir(parents=True)
    s0.write_json(retry / "run.json", manifest | {"resume": str(workspace)})
    monkeypatch.chdir(checkout)
    s0.run_hook("prepare", retry)
    s0.run_hook("before-run", retry)
    assert (checkout / "untracked.txt").read_text() == "模拟返工前文件"
    assert (workspace / "reports/P0-01-result.json").is_file()
    assert not (checkout / "reports/P0-01-result.json").exists()
    assert (retry / "previous-result.json").is_file()
    monkeypatch.chdir(root)


def test_supervisor_is_bounded(project, monkeypatch, tmp_path):
    _, state = project
    run, _, manifest = run_directory(state, s0.clean_baseline())
    fake = tmp_path / "symphony-simulator"
    fake.write_text("#!/bin/bash\nexec /bin/sleep 30\n")
    fake.chmod(0o700)
    monkeypatch.setattr(s0, "RUN_LIMIT", 0.1)
    assert s0.supervise(run, manifest, fake) == "deadline"


def test_smoke_profile_routes_separately_and_disables_followup():
    payload = issue()
    payload["labels"].append({"name": s0.SMOKE_LABEL})
    assert s0.issue_allowed(payload, 42, s0.START_PHASES, smoke=True)
    assert not s0.issue_allowed(payload, 42, s0.START_PHASES)
    assert not s0.issue_allowed(issue(), 42, s0.START_PHASES, smoke=True)
    payload["labels"][0] = {"name": "radar:human-review"}
    assert not s0.issue_allowed(payload, 42, s0.RUN_PHASES, smoke=True)
    _, header, prompt = s0.workflow("simulated-owner/radar", smoke=True).split("---\n", 2)
    config = json.loads(header)
    assert config["tracker"]["required_labels"] == ["radar:run", s0.SMOKE_LABEL]
    assert config["agent"]["max_turns"] == 1
    assert s0.SMOKE_TASK in prompt


def test_smoke_workspace_uses_only_documents_and_requires_current_approval(tmp_path, monkeypatch):
    run, workspace, manifest = run_directory(tmp_path.resolve(), None)
    manifest.update(task=s0.SMOKE_TASK, pytest="/simulated/pytest")
    s0.write_json(run / "run.json", manifest)
    monkeypatch.chdir(workspace)
    s0.run_hook("prepare", run)
    assert sorted(str(p.relative_to(workspace)) for p in workspace.rglob("*") if p.is_file()) == sorted(s0.SMOKE_FILES)
    monkeypatch.setattr(s0, "read_issue", lambda repo, num: issue(phase="human-review"))
    with pytest.raises(s0.GateError, match="no longer"):
        s0.run_hook("before-run", run)
    assert not (run / "started").exists()
    payload = issue()
    payload["labels"].append({"name": s0.SMOKE_LABEL})
    monkeypatch.setattr(s0, "read_issue", lambda repo, num: payload)
    s0.run_hook("before-run", run)
    assert s0.load_json(workspace / ".radar-task.json")["pytest"] == "/simulated/pytest"
    with pytest.raises(FileExistsError):
        s0.run_hook("before-run", run)


def test_smoke_review_requires_saved_pytest_evidence(tmp_path):
    run, workspace, manifest = run_directory(tmp_path.resolve(), None)
    manifest["task"] = s0.SMOKE_TASK
    folder = workspace / "reports"
    folder.mkdir()
    (folder / f"{s0.SMOKE_TASK}-delivery.md").write_text("模拟交付")
    s0.write_json(folder / f"{s0.SMOKE_TASK}-result.json", {
        "task": s0.SMOKE_TASK, "issue": 42, "result": "passed",
        "tests": [{"command": "simulated pytest", "exit_code": 0}],
    })
    with pytest.raises(s0.GateError, match="local evidence"):
        s0.validate_result(workspace, manifest)
    source = workspace / "smoke_test"
    source.mkdir()
    for filename in ("hello.py", "test_hello.py"):
        (source / filename).write_text("# simulation fixture\n")
    with pytest.raises(s0.GateError, match="Missing smoke artifact"):
        s0.validate_result(workspace, manifest)
    (folder / f"{s0.SMOKE_TASK}-pytest.txt").write_text("simulation fixture")
    assert s0.validate_result(workspace, manifest).is_file()
