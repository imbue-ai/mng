"""Bump version across all publishable packages and publish to PyPI.

Bumps the version in all pyproject.toml files, commits, tags, and pushes
directly to main. The publish.yml workflow triggers automatically on the
v* tag push. After pushing, monitors the publish workflow and offers to
retry on failure.

Usage:
    uv run python scripts/release.py patch      # 0.1.0 -> 0.1.1
    uv run python scripts/release.py minor      # 0.1.0 -> 0.2.0
    uv run python scripts/release.py major      # 0.1.0 -> 1.0.0
    uv run python scripts/release.py 0.2.0      # explicit version
    uv run python scripts/release.py patch --dry-run  # preview without changes
    uv run python scripts/release.py --retry    # monitor/retry the publish for the current version
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from typing import Final
from typing import cast

import semver
import tomlkit
from utils import PUBLISHABLE_PACKAGE_PYPROJECT_PATHS
from utils import REPO_ROOT
from utils import check_versions_in_sync

from imbue.mng.utils.polling import poll_for_value

BUMP_KINDS: Final[tuple[str, ...]] = ("major", "minor", "patch")
PUBLISH_WORKFLOW: Final[str] = "publish.yml"
ACTIONS_URL: Final[str] = "https://github.com/imbue-ai/mng/actions/workflows/publish.yml"
POLL_INTERVAL_SECONDS: Final[int] = 10
MAX_WAIT_FOR_RUN_SECONDS: Final[int] = 300
SLOW_START_WARNING_SECONDS: Final[int] = 60


def run(*args: str) -> str:
    """Run a command in the repo root. Returns stripped stdout."""
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()


def get_current_version() -> str:
    """Read and validate the current version across all packages."""
    return check_versions_in_sync()


def bump_version(new_version: str) -> list[Path]:
    """Update the version in all package pyproject.toml files. Returns modified files."""
    modified = []
    for path in PUBLISHABLE_PACKAGE_PYPROJECT_PATHS:
        doc = tomlkit.loads(path.read_text())
        # Cast needed because tomlkit stubs don't reflect that Table is a dict
        project = cast(dict[str, Any], doc["project"])
        if project["version"] != new_version:
            project["version"] = new_version
            path.write_text(tomlkit.dumps(doc))
            modified.append(path)
    return modified


def gh_is_available() -> bool:
    """Check whether the gh CLI is installed and authenticated."""
    try:
        run("gh", "auth", "status")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _try_find_run_id(tag: str) -> str | None:
    """Check if a publish workflow run exists for the given tag. Returns run ID or None."""
    result = run(
        "gh",
        "run",
        "list",
        "-w",
        PUBLISH_WORKFLOW,
        "-b",
        tag,
        "--json",
        "databaseId,status",
        "-L",
        "1",
    )
    if result:
        runs = json.loads(result)
        if runs:
            return str(runs[0]["databaseId"])
    return None


def _get_workflow_attempt_number(run_id: str) -> int:
    """Get the current attempt number for a workflow run."""
    result = run("gh", "run", "view", run_id, "--json", "attempt")
    return json.loads(result)["attempt"]


def _try_get_conclusion(run_id: str, after_workflow_attempt: int) -> str | None:
    """Check if a workflow run has completed after a given attempt.

    Returns the conclusion if the run is completed with attempt > after_workflow_attempt.
    Pass after_workflow_attempt=0 to match any attempt.
    """
    result = run("gh", "run", "view", run_id, "--json", "status,conclusion,attempt")
    data = json.loads(result)
    if data["status"] == "completed" and data["attempt"] > after_workflow_attempt:
        return data["conclusion"]
    return None


def find_publish_run_id(tag: str) -> str:
    """Find the workflow run ID for the publish workflow triggered by a tag push.

    Polls until the run appears (there may be a brief delay after pushing).
    """
    # Try for 60s, then warn and keep waiting
    run_id, _, _ = poll_for_value(lambda: _try_find_run_id(tag), timeout=SLOW_START_WARNING_SECONDS, poll_interval=2)
    if run_id is None:
        print("This is taking longer than expected, still waiting...")
        remaining_seconds = MAX_WAIT_FOR_RUN_SECONDS - SLOW_START_WARNING_SECONDS
        run_id, _, _ = poll_for_value(lambda: _try_find_run_id(tag), timeout=remaining_seconds, poll_interval=2)

    if run_id is not None:
        print(f"Tracking publish workflow (run {run_id})")
        return run_id

    print("ERROR: Could not find publish workflow run.", file=sys.stderr)
    print(f"Check manually: {ACTIONS_URL}", file=sys.stderr)
    sys.exit(1)


def wait_for_run_completion(run_id: str, after_workflow_attempt: int) -> str:
    """Poll until the workflow run completes. Returns the conclusion (e.g. 'success', 'failure')."""
    conclusion, _, _ = poll_for_value(
        lambda: _try_get_conclusion(run_id, after_workflow_attempt), timeout=1800, poll_interval=POLL_INTERVAL_SECONDS
    )
    if conclusion is not None:
        return conclusion
    print("ERROR: Workflow did not complete within 30 minutes.", file=sys.stderr)
    print(f"Check manually: https://github.com/imbue-ai/mng/actions/runs/{run_id}", file=sys.stderr)
    sys.exit(1)


def print_run_failure(run_id: str) -> None:
    """Print the failure logs for a workflow run."""
    print("\n--- Workflow failure logs ---\n")
    try:
        logs = run("gh", "run", "view", run_id, "--log-failed")
        print(logs)
    except subprocess.CalledProcessError:
        print("(Could not retrieve failure logs)")
    print(f"\nFull details: https://github.com/imbue-ai/mng/actions/runs/{run_id}")


def monitor_publish_workflow(tag: str) -> None:
    """Monitor the publish workflow and offer retries on failure.

    Finds the workflow run for the given tag, waits for it to complete,
    and if it fails, shows the error logs and prompts the user to retry.
    """
    run_id = find_publish_run_id(tag)
    after_workflow_attempt = 0

    while True:
        conclusion = wait_for_run_completion(run_id, after_workflow_attempt)

        if conclusion == "success":
            print("Publish workflow succeeded!")
            return

        print_run_failure(run_id)

        retry = input("\nRetry the publish workflow? [y/N] ")
        if retry.lower() != "y":
            print("Aborted. You can retry manually from the GitHub Actions page.")
            sys.exit(1)

        after_workflow_attempt = _get_workflow_attempt_number(run_id)
        print("\nRetrying...")
        run("gh", "run", "rerun", run_id, "--failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump version and publish to PyPI.")
    parser.add_argument(
        "version",
        nargs="?",
        help="Bump kind (major, minor, patch) or explicit version (e.g. 0.2.0)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Monitor/retry the publish workflow for the current version (no version bump)",
    )
    args = parser.parse_args()

    # --retry mode: just monitor the existing publish workflow
    if args.retry:
        current_version = get_current_version()
        tag = f"v{current_version}"
        print(f"Monitoring publish workflow for {tag}...")
        monitor_publish_workflow(tag)
        return

    if args.version is None:
        parser.error("version is required (unless using --retry)")

    current_version = get_current_version()

    current = semver.Version.parse(current_version)

    if args.version in BUMP_KINDS:
        new_version = str(current.next_version(args.version))
    else:
        new_version = str(semver.Version.parse(args.version))

    if new_version == current_version:
        print(f"ERROR: New version {new_version} is the same as the current version.", file=sys.stderr)
        sys.exit(1)

    print(f"Current version: {current_version}")
    print(f"New version:     {new_version}")
    print("Files to update:")
    for path in PUBLISHABLE_PACKAGE_PYPROJECT_PATHS:
        print(f"  {path.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("\n(dry run -- no changes made)")
        return

    # Ensure we're on main and up to date before prompting for confirmation
    branch = run("git", "branch", "--show-current")
    if branch != "main":
        print(f"ERROR: Must be on main branch (currently on {branch})", file=sys.stderr)
        sys.exit(1)

    if run("git", "status", "--porcelain"):
        print("ERROR: Working tree is not clean. Commit or stash changes first.", file=sys.stderr)
        sys.exit(1)

    run("git", "fetch", "origin", "main")
    local_sha = run("git", "rev-parse", "HEAD")
    remote_sha = run("git", "rev-parse", "origin/main")
    if local_sha != remote_sha:
        print(
            f"ERROR: Local main ({local_sha[:8]}) is not up to date with origin ({remote_sha[:8]}).", file=sys.stderr
        )
        print("Run 'git pull' first.", file=sys.stderr)
        sys.exit(1)

    confirm = input(f"\nProceed with release {new_version}? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    # Bump versions
    modified = bump_version(new_version)
    print(f"\nUpdated {len(modified)} file(s)")

    # Regenerate lock
    print("\nRegenerating uv.lock...")
    run("uv", "lock")

    # Commit, tag, push
    tag = f"v{new_version}"
    files_to_add = [str(p.relative_to(REPO_ROOT)) for p in modified] + ["uv.lock"]
    run("git", "add", *files_to_add)
    run("git", "commit", "-m", f"Bump version to {new_version}")
    run("git", "tag", tag)
    run("git", "push", "origin", "main", tag)

    print(f"\nRelease {new_version} pushed.")

    # Monitor the publish workflow if gh is available
    if gh_is_available():
        monitor_publish_workflow(tag)
    else:
        print("Install the gh CLI to monitor the publish workflow automatically.")
        print(f"  {ACTIONS_URL}")


if __name__ == "__main__":
    main()
