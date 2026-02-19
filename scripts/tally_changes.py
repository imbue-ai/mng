#!/usr/bin/env python3
"""Tally git changes by day (PST) across one or more git repos, excluding merge commits.

Usage: python3 tally_changes.py <repo_path> [repo_path ...]
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict


def _detect_main_branch(repo_path: str) -> str:
    """Return 'main' or 'master', whichever exists in the repo."""
    for branch in ("main", "master"):
        ret = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            capture_output=True,
            cwd=repo_path,
        )
        if ret.returncode == 0:
            return branch
    raise SystemExit(f"Error: no 'main' or 'master' branch found in {repo_path}")


def tally_repo(repo_path: str, env: dict[str, str]) -> dict[str, int]:
    """Return a dict mapping date -> total changes for a single repo."""
    branch = _detect_main_branch(repo_path)
    result = subprocess.run(
        [
            "git",
            "log",
            branch,
            "--no-merges",
            "--format=COMMIT %ad",
            "--date=format-local:%Y-%m-%d",
            "--shortstat",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=repo_path,
    )

    changes_by_day: dict[str, int] = defaultdict(int)
    current_date: str | None = None

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("COMMIT "):
            current_date = line.removeprefix("COMMIT ")
            continue

        # shortstat line, e.g. " 3 files changed, 10 insertions(+), 5 deletions(-)"
        if current_date and "changed" in line:
            insertions = 0
            deletions = 0
            ins_match = re.search(r"(\d+) insertion", line)
            del_match = re.search(r"(\d+) deletion", line)
            if ins_match:
                insertions = int(ins_match.group(1))
            if del_match:
                deletions = int(del_match.group(1))
            changes_by_day[current_date] += insertions + deletions
            current_date = None

    return dict(changes_by_day)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <repo_path> [repo_path ...]", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()
    env["TZ"] = "America/Los_Angeles"

    totals: dict[str, int] = defaultdict(int)
    for repo_path in sys.argv[1:]:
        for date, changes in tally_repo(repo_path, env).items():
            totals[date] += changes

    sorted_totals = dict(sorted(totals.items()))
    print(json.dumps(sorted_totals, indent=2))


if __name__ == "__main__":
    main()
