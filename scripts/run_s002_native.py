#!/usr/bin/env python3
"""Use a normal Mac terminal to publish the baseline and run the existing S0-02 smoke entry."""

import argparse
from getpass import getpass
from pathlib import Path
import json
import os
import re
import subprocess
import sys

import symphony_s0 as s0

REPO = "hxnick/keys-radar"
ORIGIN = f"https://github.com/{REPO}.git"
ISSUE_TITLE = "S0-SMOKE-01 Symphony 与 Codex 研发闭环测试"
ISSUE_MARKER = "<!-- keys-radar:s0-smoke-01 -->"
BINARY = s0.ROOT / ".symphony-state/runtime/symphony-v0.0.3-macos_arm64"
LABELS = {
    "radar:todo": "0366d6", "radar:s0-smoke": "5319e7",
    "radar:run": "0e8a16", "radar:human-review": "fbca04",
}
SOURCE_FILES = (
    ".env.example", ".gitignore", ".python-version", "AGENTS.md", "README.md", "WORKFLOW.md",
    "alembic.ini", "pyproject.toml", "uv.lock",
    "docs/ACCEPTANCE_CRITERIA.md", "docs/ARCHITECTURE.md", "docs/COMPETITIVE_ANALYSIS.md",
    "docs/DATA_SCHEMA.md", "docs/OPPORTUNITY_REPORT_SCHEMA.md", "docs/P0_ACCEPTANCE.md",
    "docs/PROJECT_BRIEF.md", "docs/ROADMAP.md", "docs/SCORING_RULES.md",
    "docs/SOURCE_COMPLIANCE.md", "docs/SYMPHONY.md",
    "migrations/env.py", "migrations/script.py.mako", "migrations/versions/0001_p0_schema.py",
    "radar/__init__.py", "radar/__main__.py", "radar/api.py", "radar/config.py",
    "radar/constants.py", "radar/db.py", "radar/errors.py", "radar/imports.py",
    "radar/main.py", "radar/models.py", "radar/schemas.py",
    "reports/README.md", "reports/S0_ACCEPTANCE.md",
    "scripts/probe_codex_stdio.py", "scripts/run_s002_native.py", "scripts/symphony_s0.py",
    "tasks/P0-01.md", "tasks/P0-02.md", "tasks/P0-03.md", "tasks/P0-04.md",
    "tasks/P0-05.md", "tasks/P0.md", "tasks/S0-SMOKE-01.md",
    "tests/conftest.py", "tests/test_api.py", "tests/test_migrations.py",
    "tests/test_symphony_s0.py",
)
SECRET = re.compile(rb"github_pat_[A-Za-z0-9_]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{25,}|BEGIN ([A-Z]+ )?PRIVATE KEY")
GIT = ("git", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
       "-c", "credential.helper=!gh auth git-credential")
GH_TOKEN_ALIASES = {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}


def call(*command, capture=True, timeout=30, **options):
    return subprocess.run(command, cwd=s0.ROOT, text=True, timeout=timeout,
                          check=True, stdout=subprocess.PIPE if capture else None, **options).stdout


def gh(*arguments):
    return call("gh", *arguments, env=operator_env())


def git(*arguments):
    return call(*GIT, *arguments, env=operator_env()).strip()


def operator_env():
    return {key: value for key, value in os.environ.items() if key not in GH_TOKEN_ALIASES} | {
        "GH_HOST": "github.com",
    }


def pages(endpoint):
    data = json.loads(gh("api", endpoint, "--paginate", "--slurp"))
    return [entry for page in data for entry in page]


def remote_refs():
    return {ref: sha for sha, ref in (line.split() for line in git("ls-remote", "--refs", ORIGIN).splitlines())}


def publish_baseline(account, repo):
    refs = remote_refs()
    s0.require(repo["isEmpty"] == (not refs), "GitHub metadata and actual Git refs disagree. Stop and inspect.")
    root = s0.ROOT
    if not (root / ".git").exists():
        s0.require(not refs, "Remote already contains refs and this directory has no Git baseline.")
        git("init", "-b", "main")
    s0.require(git("rev-parse", "--show-toplevel") == str(root), "Unexpected Git project root.")
    if "origin" not in git("remote").splitlines():
        git("remote", "add", "origin", ORIGIN)
    for flag in ([], ["--push"]):
        s0.require(git("remote", "get-url", "--all", *flag, "origin") == ORIGIN, "Existing origin differs from the authorized URL.")

    if refs:
        head = git("rev-parse", "--verify", "HEAD")
        default = repo.get("defaultBranchRef") or {}
        s0.require(default.get("name") == "main" and refs.get("refs/heads/main") == head,
                   "Existing remote and local histories differ. No push attempted.")
        print(f"Existing main matches local HEAD: {head}", flush=True)
        return

    s0.require(git("symbolic-ref", "--short", "HEAD") == "main", "Expected the local main branch.")
    receipt = s0.state_root() / "s002-baseline-commit.json"
    if git("for-each-ref"):
        s0.require(receipt.is_file() and s0.load_json(receipt)["head"] == git("rev-parse", "HEAD"),
                   "Local history was not created by this launcher. Stop and inspect.")
    else:
        s0.require(not git("diff", "--cached", "--name-only"), "Staged changes already exist. Stop and inspect.")
        for name in SOURCE_FILES:
            path = root / name
            s0.require(path.is_file() and path.resolve() == path, f"Unexpected source file: {name}")
            s0.require(not SECRET.search(path.read_bytes()), f"Credential-like content detected in {name}.")
        git("add", "--", *SOURCE_FILES)
        s0.require(set(git("diff", "--cached", "--name-only").splitlines()) == set(SOURCE_FILES),
                   "Staged names differ from the public source list. Nothing committed.")
        s0.require(not remote_refs(), "Remote gained refs while staging. Nothing committed or pushed.")
        # Use GitHub's no-reply commit identity for this public baseline.
        noreply = f"{account['id']}+{account['login']}@users.noreply.github.com"
        git("-c", f"user.name={account['login']}", "-c", f"user.email={noreply}",
            "commit", "-m", "Initialize Keys Radar S0-02 baseline")
        s0.write_json(receipt, {"head": git("rev-parse", "HEAD")})
    s0.require(not remote_refs(), "Remote gained refs before push. Stop and inspect.")
    git("push", "-u", "origin", "HEAD:refs/heads/main")
    head = git("rev-parse", "HEAD")
    s0.require(remote_refs().get("refs/heads/main") == head, "Pushed main could not be verified.")
    print(f"Published and verified main: {head}", flush=True)


def get_or_create_issue():
    candidates = [entry for entry in pages(f"repos/{REPO}/issues?state=all&per_page=100")
                  if "pull_request" not in entry and
                  (entry.get("title") == ISSUE_TITLE or ISSUE_MARKER in (entry.get("body") or ""))]
    s0.require(len(candidates) <= 1, "Multiple S0-SMOKE-01 issues exist. Review them before proceeding.")
    if not candidates:
        body = ISSUE_MARKER + "\n\n" + (s0.ROOT / "tasks/S0-SMOKE-01.md").read_text()
        github_url = call("gh", "issue", "create", "-R", REPO, "--title", ISSUE_TITLE,
                          "--body-file", "-", input=body, env=operator_env()).strip()
        number = int(github_url.rsplit("/", 1)[1])
        return json.loads(gh("api", f"repos/{REPO}/issues/{number}"))
    issue = candidates[0]
    s0.require(issue["title"] == ISSUE_TITLE and ISSUE_MARKER in (issue.get("body") or ""),
               "The existing candidate is not bound to this S0-02 launcher.")
    return issue


def labels_of(issue):
    return {label["name"].lower() for label in issue["labels"]}


def launch_smoke(issue, token):
    number = issue["number"]
    url = f"https://github.com/{REPO}/issues/{number}"
    s0.require(issue["state"] == "open", f"The bound issue is closed: {url}")
    current = labels_of(issue)
    if "radar:human-review" in current and "radar:run" not in current:
        print(f"Already waiting for human review: {url}")
        return
    other_phases = {f"radar:{phase}" for phase in s0.PHASES - {"todo"}}
    s0.require(not (current & other_phases),
               "Existing issue has another workflow phase. Stop and inspect.")
    candidates = pages(f"repos/{REPO}/issues?state=open&labels=radar%3Arun%2Cradar%3As0-smoke&per_page=100")
    s0.require(all(entry["number"] == number or "pull_request" in entry for entry in candidates),
               "Another runnable smoke issue exists. Stop and inspect.")

    present = {label["name"].lower() for label in pages(f"repos/{REPO}/labels?per_page=100")}
    for name, color in LABELS.items():
        if name not in present:
            gh("label", "create", name, "-R", REPO, "--color", color)

    env = operator_env() | {s0.TOKEN_ENV: token}
    # Check repository visibility with the separate token before enabling dispatch.
    tracked = json.loads(call("gh", "api", f"repos/{REPO}/issues/{number}",
                              env=env | {"GH_HOST": "github.com", "GH_TOKEN": token}))
    s0.require(tracked.get("number") == number and tracked.get("state") == "open",
               "The read-only credential cannot access the bound open issue.")
    edit = ("issue", "edit", str(number), "-R", REPO)
    completed = False
    try:
        gh(*edit, "--add-label", "radar:todo,radar:s0-smoke,radar:run")
        print(f"Scheduling {url}", flush=True)
        output = call(sys.executable, "scripts/symphony_s0.py", "smoke-run",
                      "--repo", REPO, "--issue", str(number), "--symphony", str(BINARY),
                      env=env, timeout=340)
        print(output, end="", flush=True)
        found = re.findall(r"^Local run: (S0-SMOKE-01-[a-z0-9_]+)$", output, flags=re.MULTILINE)
        s0.require(len(found) == 1, "No unique smoke run was reported.")
        run = s0.local_run(s0.state_root(), found[0])
        s0.require(s0.load_json(run / "stop.json")["result"] == "attempt_ended", "Worker did not complete its attempt.")
        s0.verify_retained(s0.state_root(), found[0])
        log = s0.workspace_path(run, number) / "reports/S0-SMOKE-01-pytest.txt"
        pytest_output = log.read_text(errors="replace")
        s0.require(re.search(r"\b[1-9][0-9]* passed\b", pytest_output) and
                   not re.search(r"\b[1-9][0-9]* (?:failed|errors?)\b", pytest_output),
                   "Saved pytest output does not show a clean pass.")
        completed = True
    finally:
        # Revoke scheduling even when a foreground attempt fails, leaving the issue open.
        gh(*edit, "--remove-label", "radar:run")
    if completed:
        gh(*edit, "--remove-label", "radar:todo", "--add-label", "radar:human-review")
        reviewed = json.loads(gh("api", f"repos/{REPO}/issues/{number}"))
        visible = labels_of(reviewed)
        s0.require(reviewed["state"] == "open" and "radar:human-review" in visible and "radar:run" not in visible,
                   "Could not verify the remote human-review state.")
        print(f"Waiting for human review: {url}")
        print(f"Evidence: {run}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish-only", action="store_true", help="Stop after verifying the public Git baseline")
    args = parser.parse_args()
    try:
        account = json.loads(gh("api", "user"))
        s0.require(account["login"].lower() == "hxnick", "GitHub CLI must be signed in as hxnick.")
        repo = json.loads(gh("repo", "view", REPO, "--json", "nameWithOwner,isEmpty,defaultBranchRef"))
        s0.require(repo["nameWithOwner"].lower() == REPO, "GitHub returned another repository.")
        call(sys.executable, "scripts/probe_codex_stdio.py", capture=False)
        publish_baseline(account, repo)
        if args.publish_only:
            return 0
        s0.require(BINARY.is_file() and os.access(BINARY, os.X_OK), "Installed Symphony executable not found.")
        token = os.environ.get(s0.TOKEN_ENV)
        if not token:
            s0.require(sys.stdin.isatty(), "Open this command in Mac Terminal to enter the read-only token.")
            token = getpass("Repository-scoped Issues read-only token (hidden): ").strip()
        operator_token = gh("auth", "token", "--hostname", "github.com").strip()
        s0.require(token and token != operator_token, "Use a separate Issues read-only credential for Symphony.")
        launch_smoke(get_or_create_issue(), token)
    except (s0.GateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Do not emit any captured HTTP output or credentials on a failed command.
        print(f"Blocked: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
