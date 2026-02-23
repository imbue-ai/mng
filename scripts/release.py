"""Selectively bump and publish changed packages to PyPI.

Only packages that changed since the last release (or their dependents) are bumped.
The tag is always based on the mng version, so mng is always bumped to ensure a
unique tag. This cascades to mng's dependents (they must update their pin).

Usage:
    uv run scripts/release.py patch      # bump changed packages by patch
    uv run scripts/release.py minor      # bump changed packages by minor
    uv run scripts/release.py major      # bump changed packages by major
    uv run scripts/release.py patch --dry-run  # preview without changes
    uv run scripts/release.py --watch    # watch the publish workflow for the current version
    uv run scripts/release.py --retry    # rerun failed jobs and watch
"""

import argparse
import json
import subprocess
import sys
from collections import deque
from typing import Any
from typing import Final
from typing import cast

import semver
import tomlkit
from utils import PACKAGES
from utils import PACKAGE_BY_PYPI_NAME
from utils import REPO_ROOT
from utils import get_package_versions
from utils import normalize_pypi_name
from utils import parse_dep_name

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


def get_mng_version() -> str:
    """Read the current mng package version (used for tag naming)."""
    versions = get_package_versions()
    return versions["mng"]


def _find_last_release_tag() -> str:
    """Find the most recent v* tag reachable from HEAD. Fetches tags from origin first."""
    run("git", "fetch", "--tags", "origin")
    try:
        return run("git", "describe", "--tags", "--match", "v*", "--abbrev=0")
    except subprocess.CalledProcessError:
        print("ERROR: No v* tags found. Cannot determine what changed.", file=sys.stderr)
        sys.exit(1)


def _detect_changed_packages(since_tag: str) -> set[str]:
    """Return the set of pypi names for packages whose source changed since the given tag."""
    changed: set[str] = set()
    for pkg in PACKAGES:
        # git diff --quiet exits 1 if there are differences
        result = subprocess.run(
            ["git", "diff", "--quiet", since_tag, "HEAD", "--", f"libs/{pkg.dir_name}/"],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        if result.returncode != 0:
            changed.add(pkg.pypi_name)
    return changed


def _cascade_reverse_deps(
    seeds: deque[str],
    reverse_deps: dict[str, list[str]],
    to_bump: dict[str, str],
) -> None:
    """BFS through reverse deps, marking unvisited dependents as "cascade"."""
    while seeds:
        current = seeds.popleft()
        for dependent in reverse_deps.get(current, []):
            if dependent not in to_bump:
                to_bump[dependent] = "cascade"
                seeds.append(dependent)


def _compute_bump_set(directly_changed: set[str]) -> dict[str, str]:
    """Compute the full set of packages to bump and the reason for each.

    Returns {pypi_name: reason} where reason is "changed", "cascade", or "always".
    """
    # Build reverse dependency map
    reverse_deps: dict[str, list[str]] = {pkg.pypi_name: [] for pkg in PACKAGES}
    for pkg in PACKAGES:
        for dep in pkg.internal_deps:
            reverse_deps[normalize_pypi_name(dep)].append(pkg.pypi_name)

    # BFS from directly changed packages through reverse deps
    to_bump: dict[str, str] = {}
    for name in directly_changed:
        to_bump[name] = "changed"
    _cascade_reverse_deps(deque(directly_changed), reverse_deps, to_bump)

    # mng is always bumped (tag is v<mng-version>)
    if "mng" not in to_bump:
        to_bump["mng"] = "always"
        _cascade_reverse_deps(deque(["mng"]), reverse_deps, to_bump)

    return to_bump


def bump_package_versions(
    to_bump: dict[str, str],
    bump_kind: str,
    current_versions: dict[str, str],
) -> dict[str, str]:
    """Apply bump_kind to each package in to_bump. Returns {pypi_name: new_version}."""
    new_versions: dict[str, str] = {}
    for name in to_bump:
        current = semver.Version.parse(current_versions[name])
        new_versions[name] = str(current.next_version(bump_kind))
    return new_versions


def _write_version(pkg_pypi_name: str, new_version: str) -> None:
    """Update the version field in a package's pyproject.toml."""
    pkg = PACKAGE_BY_PYPI_NAME[pkg_pypi_name]
    doc = tomlkit.loads(pkg.pyproject_path.read_text())
    project = cast(dict[str, Any], doc["project"])
    project["version"] = new_version
    pkg.pyproject_path.write_text(tomlkit.dumps(doc))


def update_internal_dep_pins(all_versions: dict[str, str]) -> list[str]:
    """Rewrite internal dep entries to use == pins matching current versions.

    Returns list of packages whose pyproject.toml was modified.
    """
    modified: list[str] = []
    for pkg in PACKAGES:
        if not pkg.internal_deps:
            continue
        doc = tomlkit.loads(pkg.pyproject_path.read_text())
        project = cast(dict[str, Any], doc["project"])
        # Modify the tomlkit array in-place to preserve formatting and comments
        deps = project["dependencies"]
        is_changed = False
        for idx in range(len(deps)):
            dep_str = str(deps[idx])
            dep_name = parse_dep_name(dep_str)
            dep_normalized = normalize_pypi_name(dep_name)
            if dep_normalized in all_versions:
                canonical_name = PACKAGE_BY_PYPI_NAME[dep_normalized].pypi_name
                new_dep = f"{canonical_name}=={all_versions[dep_normalized]}"
                if dep_str != new_dep:
                    deps[idx] = new_dep
                    is_changed = True
        if is_changed:
            pkg.pyproject_path.write_text(tomlkit.dumps(doc))
            modified.append(pkg.pypi_name)
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


def _get_workflow_attempt_number(run_id: str) -> int:
    """Get the current attempt number for a workflow run."""
    result = run("gh", "run", "view", run_id, "--json", "attempt")
    return json.loads(result)["attempt"]


def watch_publish_workflow(run_id: str, after_workflow_attempt: int = 0) -> None:
    """Watch a publish workflow run until it completes.

    On failure, prints the error logs and the commands to watch/retry.
    """
    conclusion = wait_for_run_completion(run_id, after_workflow_attempt)

    if conclusion == "success":
        print("Publish workflow succeeded!")
        return

    print_run_failure(run_id)
    print()
    print("To retry failed jobs and watch:")
    print("  uv run scripts/release.py --retry")
    sys.exit(1)


def _print_bump_summary(
    directly_changed: set[str],
    to_bump: dict[str, str],
    current_versions: dict[str, str],
    new_versions: dict[str, str],
) -> None:
    """Print a summary of what will be bumped and why."""
    print("Directly changed packages:")
    if directly_changed:
        for name in sorted(directly_changed):
            print(f"  {name}")
    else:
        print("  (none)")

    print()
    print("Packages to bump:")
    for pkg in PACKAGES:
        if pkg.pypi_name in to_bump:
            reason = to_bump[pkg.pypi_name]
            old_v = current_versions[pkg.pypi_name]
            new_v = new_versions[pkg.pypi_name]
            print(f"  {pkg.pypi_name}: {old_v} -> {new_v} ({reason})")

    print()
    print("Packages unchanged:")
    unchanged = [pkg.pypi_name for pkg in PACKAGES if pkg.pypi_name not in to_bump]
    if unchanged:
        for name in unchanged:
            print(f"  {name} (stays at {current_versions[name]})")
    else:
        print("  (none)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Selectively bump and publish changed packages to PyPI.")
    parser.add_argument(
        "bump_kind",
        nargs="?",
        choices=BUMP_KINDS,
        help="Bump kind: major, minor, or patch",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the publish workflow for the current version (no version bump)",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Rerun failed publish jobs for the current version, then watch",
    )
    args = parser.parse_args()

    # --watch / --retry mode
    if args.watch or args.retry:
        mng_version = get_mng_version()
        tag = f"v{mng_version}"
        run_id = find_publish_run_id(tag)

        after_attempt = 0
        if args.retry:
            after_attempt = _get_workflow_attempt_number(run_id)
            print(f"Rerunning failed jobs for {tag}...")
            run("gh", "run", "rerun", run_id, "--failed")

        print(f"Watching publish workflow for {tag}...")
        watch_publish_workflow(run_id, after_workflow_attempt=after_attempt)
        return

    if args.bump_kind is None:
        parser.error("bump_kind is required: patch, minor, or major")

    bump_kind: str = args.bump_kind

    # Detect what changed since the last release
    last_tag = _find_last_release_tag()
    print(f"Last release tag: {last_tag}")
    directly_changed = _detect_changed_packages(last_tag)

    if not directly_changed:
        print("\nNo packages changed since the last release. Nothing to do.")
        return

    # Compute the full bump set (includes cascades and mng-always rule)
    to_bump = _compute_bump_set(directly_changed)
    current_versions = get_package_versions()
    new_versions = bump_package_versions(to_bump, bump_kind, current_versions)

    # Compute what the full version map will look like after bumping
    all_versions_after = dict(current_versions)
    all_versions_after.update(new_versions)

    new_mng_version = all_versions_after["mng"]
    tag = f"v{new_mng_version}"

    # Show summary
    _print_bump_summary(directly_changed, to_bump, current_versions, new_versions)
    print()
    print(f"Tag: {tag}")

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

    confirm = input(f"\nProceed with release {tag}? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    # Bump versions for selected packages
    for name, new_version in new_versions.items():
        _write_version(name, new_version)
    print(f"\nBumped versions for {len(new_versions)} package(s).")

    # Update internal dependency pins to match new versions
    pin_modified = update_internal_dep_pins(all_versions_after)
    if pin_modified:
        print(f"Updated dependency pins in: {', '.join(pin_modified)}")

    print("Regenerating uv.lock...")
    run("uv", "lock")

    # Commit, tag, push
    bumped_names = sorted(new_versions.keys())
    commit_msg = f"Release {tag} ({', '.join(bumped_names)})"

    files_to_add = [str(pkg.pyproject_path.relative_to(REPO_ROOT)) for pkg in PACKAGES] + ["uv.lock"]
    run("git", "add", *files_to_add)
    run("git", "commit", "-m", commit_msg)
    run("git", "tag", tag)
    run("git", "push", "origin", "main", tag)

    print(f"\nRelease {tag} pushed. Publish workflow: {ACTIONS_URL}")

    # Watch the publish workflow if gh is available
    if gh_is_available():
        run_id = find_publish_run_id(tag)
        watch_publish_workflow(run_id)
    else:
        print()
        print("To watch the publish (requires gh CLI):")
        print("  uv run scripts/release.py --watch")


if __name__ == "__main__":
    main()
