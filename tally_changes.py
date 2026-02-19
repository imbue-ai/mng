#!/usr/bin/env python3
"""Tally git changes by day (PST) for the main branch, excluding merge commits."""

import json
import os
import re
import subprocess
from collections import defaultdict


def main() -> None:
    env = os.environ.copy()
    env["TZ"] = "America/Los_Angeles"

    result = subprocess.run(
        [
            "git",
            "log",
            "main",
            "--no-merges",
            "--format=COMMIT %ad",
            "--date=format-local:%Y-%m-%d",
            "--shortstat",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=env,
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

    sorted_changes = dict(sorted(changes_by_day.items()))
    print(json.dumps(sorted_changes, indent=2))


if __name__ == "__main__":
    main()
