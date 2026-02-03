"""Load triaged GitHub issues with the 'autoclaude' label.

This script fetches all open issues labeled 'autoclaude' and filters them
to only include issues that have comments from authorized users. The output
is a JSON array of issues with their filtered comments.

Usage:
    uv run python scripts/load_triaged_issues.py > triaged_issues.json
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure


class GitHubComment(FrozenModel):
    """A comment on a GitHub issue."""

    author: str = Field(description="The GitHub username of the comment author")
    body: str = Field(description="The comment text")
    created_at: str = Field(description="ISO timestamp of when the comment was created")


class GitHubIssue(FrozenModel):
    """A GitHub issue with filtered comments."""

    number: int = Field(description="The issue number")
    title: str = Field(description="The issue title")
    body: str = Field(description="The issue body/description")
    labels: tuple[str, ...] = Field(description="Labels on the issue")
    created_at: str = Field(description="ISO timestamp of when the issue was created")
    url: str = Field(description="The HTML URL for the issue")
    authorized_comments: tuple[GitHubComment, ...] = Field(description="Comments from authorized users only")


class TriagedIssuesOutput(FrozenModel):
    """Output containing triaged issues."""

    issues: tuple[GitHubIssue, ...] = Field(description="List of triaged issues")


def load_authorized_users() -> tuple[str, ...]:
    """Load the list of authorized GitHub usernames from the config file."""
    config_path = Path(__file__).parent / "authorized_github_users.json"
    if not config_path.exists():
        print(
            f"Error: authorized_github_users.json not found at {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    with config_path.open() as f:
        users = json.load(f)

    if not isinstance(users, list):
        print("Error: authorized_github_users.json must contain a JSON array", file=sys.stderr)
        sys.exit(1)

    return tuple(users)


def run_gh_command(args: list[str]) -> Any:
    """Run a gh CLI command and return the parsed JSON output."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"Error running gh command: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    if not result.stdout.strip():
        return []

    return json.loads(result.stdout)


def fetch_issues_with_autoclaude_label() -> list[dict[str, Any]]:
    """Fetch all open issues with the 'autoclaude' label."""
    return run_gh_command(
        [
            "issue",
            "list",
            "--label",
            "autoclaude",
            "--state",
            "open",
            "--json",
            "number,title,body,labels,createdAt,url",
            "--limit",
            "1000",
        ]
    )


def fetch_issue_comments(issue_number: int) -> list[dict[str, Any]]:
    """Fetch all comments for a specific issue."""
    return run_gh_command(
        [
            "issue",
            "view",
            str(issue_number),
            "--json",
            "comments",
        ]
    ).get("comments", [])


@pure
def filter_comments_by_authorized_users(
    comments: list[dict[str, Any]],
    authorized_users: tuple[str, ...],
) -> tuple[GitHubComment, ...]:
    """Filter comments to only include those from authorized users."""
    filtered: list[GitHubComment] = []
    for comment in comments:
        author = comment.get("author", {})
        author_login = author.get("login", "") if isinstance(author, dict) else ""
        if author_login in authorized_users:
            filtered.append(
                GitHubComment(
                    author=author_login,
                    body=comment.get("body", ""),
                    created_at=comment.get("createdAt", ""),
                )
            )
    return tuple(filtered)


@pure
def create_github_issue(
    raw_issue: dict[str, Any],
    authorized_comments: tuple[GitHubComment, ...],
) -> GitHubIssue:
    """Create a GitHubIssue from raw API data and filtered comments."""
    labels = tuple(
        label.get("name", "") if isinstance(label, dict) else str(label) for label in raw_issue.get("labels", [])
    )
    return GitHubIssue(
        number=raw_issue.get("number", 0),
        title=raw_issue.get("title", ""),
        body=raw_issue.get("body", ""),
        labels=labels,
        created_at=raw_issue.get("createdAt", ""),
        url=raw_issue.get("url", ""),
        authorized_comments=authorized_comments,
    )


def main() -> None:
    """Load and filter triaged issues, outputting as JSON."""
    # Load authorized users
    authorized_users = load_authorized_users()
    print(f"Loaded {len(authorized_users)} authorized users", file=sys.stderr)

    # Fetch all autoclaude issues
    raw_issues = fetch_issues_with_autoclaude_label()
    print(f"Found {len(raw_issues)} open issues with 'autoclaude' label", file=sys.stderr)

    # Process each issue
    triaged_issues: list[GitHubIssue] = []
    for raw_issue in raw_issues:
        issue_number = raw_issue.get("number")
        if issue_number is None:
            continue

        # Fetch and filter comments
        raw_comments = fetch_issue_comments(issue_number)
        authorized_comments = filter_comments_by_authorized_users(raw_comments, authorized_users)

        # Only include issues with at least one authorized comment
        if authorized_comments:
            issue = create_github_issue(raw_issue, authorized_comments)
            triaged_issues.append(issue)
            print(
                f"Issue #{issue_number}: {len(authorized_comments)} authorized comment(s)",
                file=sys.stderr,
            )

    print(f"Total triaged issues: {len(triaged_issues)}", file=sys.stderr)

    # Output the result
    output = TriagedIssuesOutput(issues=tuple(triaged_issues))
    print(output.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
