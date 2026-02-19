"""Bump version across all publishable packages and publish to PyPI.

Bumps the version in all pyproject.toml files, commits, tags, and pushes
directly to main. The publish.yml workflow triggers automatically on the
v* tag push.

Usage:
    uv run python scripts/release.py patch      # 0.1.0 -> 0.1.1
    uv run python scripts/release.py minor      # 0.1.0 -> 0.2.0
    uv run python scripts/release.py major      # 0.1.0 -> 1.0.0
    uv run python scripts/release.py 0.2.0      # explicit version
    uv run python scripts/release.py patch --dry-run  # preview without changes
"""

import argparse
import subprocess
import sys
from pathlib import Path

import semver
import tomlkit

from scripts.publishable_packages import PUBLISHABLE_PACKAGE_PYPROJECT_PATHS
from scripts.publishable_packages import REPO_ROOT

BUMP_KINDS = ("major", "minor", "patch")


def get_current_version() -> str:
    """Read the current version from the first package."""
    doc = tomlkit.loads(PUBLISHABLE_PACKAGE_PYPROJECT_PATHS[0].read_text())
    return doc["project"]["version"]


def bump_version(new_version: str) -> list[Path]:
    """Update the version in all package pyproject.toml files. Returns modified files."""
    modified = []
    for path in PUBLISHABLE_PACKAGE_PYPROJECT_PATHS:
        doc = tomlkit.loads(path.read_text())
        if doc["project"]["version"] != new_version:
            doc["project"]["version"] = new_version
            path.write_text(tomlkit.dumps(doc))
            modified.append(path)
    return modified


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command and print it."""
    print(f"  $ {' '.join(cmd)}")
    try:
        return subprocess.run(cmd, check=check, cwd=REPO_ROOT, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        if e.stdout:
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump version and publish to PyPI.")
    parser.add_argument(
        "version",
        help="Bump kind (major, minor, patch) or explicit version (e.g. 0.2.0)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")
    args = parser.parse_args()

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
    print(f"Files to update:")
    for path in PUBLISHABLE_PACKAGE_PYPROJECT_PATHS:
        print(f"  {path.relative_to(REPO_ROOT)}")

    if args.dry_run:
        print("\n(dry run -- no changes made)")
        return

    confirm = input(f"\nProceed with release {new_version}? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    # Ensure we're on main and up to date
    result = run(["git", "branch", "--show-current"])
    branch = result.stdout.strip()
    if branch != "main":
        print(f"ERROR: Must be on main branch (currently on {branch})", file=sys.stderr)
        sys.exit(1)

    result = run(["git", "status", "--porcelain"])
    if result.stdout.strip():
        print("ERROR: Working tree is not clean. Commit or stash changes first.", file=sys.stderr)
        sys.exit(1)

    run(["git", "fetch", "origin", "main"])
    local_sha = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    remote_sha = run(["git", "rev-parse", "origin/main"]).stdout.strip()
    if local_sha != remote_sha:
        print(
            f"ERROR: Local main ({local_sha[:8]}) is not up to date with origin ({remote_sha[:8]}).", file=sys.stderr
        )
        print("Run 'git pull' first.", file=sys.stderr)
        sys.exit(1)

    # Bump versions
    modified = bump_version(new_version)
    print(f"\nUpdated {len(modified)} file(s)")

    # Regenerate lock
    print("\nRegenerating uv.lock...")
    run(["uv", "lock"])

    # Commit, tag, push
    tag = f"v{new_version}"
    files_to_add = [str(p.relative_to(REPO_ROOT)) for p in modified] + ["uv.lock"]
    run(["git", "add"] + files_to_add)
    run(["git", "commit", "-m", f"Bump version to {new_version}"])
    run(["git", "tag", tag])
    run(["git", "push", "origin", "main", tag])

    print(f"\nRelease {new_version} pushed. The publish workflow will run automatically.")
    print(f"  https://github.com/imbue-ai/mngr/actions/workflows/publish.yml")


if __name__ == "__main__":
    main()
