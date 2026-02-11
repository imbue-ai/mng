import json
import subprocess
import sys
import webbrowser
from typing import Final
from urllib.parse import quote
from urllib.parse import urlencode

import click
from loguru import logger

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure

GITHUB_REPO: Final[str] = "imbue-ai/mngr"
GITHUB_BASE_URL: Final[str] = f"https://github.com/{GITHUB_REPO}"
ISSUE_TITLE_PREFIX: Final[str] = "[NotImplemented]"

# Maximum URL length to stay within browser and GitHub limits
_MAX_URL_LENGTH: Final[int] = 8000


class ExistingIssue(FrozenModel):
    """A GitHub issue that already exists for a NotImplementedError."""

    number: int
    title: str
    url: str


@pure
def build_issue_title(error_message: str) -> str:
    """Build a GitHub issue title from a NotImplementedError message."""
    first_line = error_message.strip().split("\n")[0]
    return f"{ISSUE_TITLE_PREFIX} {first_line}"


@pure
def build_issue_body(error_message: str) -> str:
    """Build a GitHub issue body from a NotImplementedError message."""
    return (
        "## Feature Request\n"
        "\n"
        "This feature is referenced in the code but not yet implemented.\n"
        "\n"
        "**Error message:**\n"
        f"```\n{error_message}\n```\n"
        "\n"
        "## Use Case\n"
        "\n"
        "_Please describe your use case here._\n"
    )


_TRUNCATION_SUFFIX: Final[str] = "\n\n_(truncated)_"


@pure
def build_new_issue_url(title: str, body: str) -> str:
    """Build a GitHub URL for creating a new issue with pre-populated fields."""
    base_prefix = f"{GITHUB_BASE_URL}/issues/new?"

    def _make_url(text: str) -> str:
        return base_prefix + urlencode({"title": title, "body": text}, quote_via=quote)

    full_url = _make_url(body)

    # Truncate body if URL exceeds max length
    if len(full_url) > _MAX_URL_LENGTH:
        # Over-estimate how much to trim (URL encoding can expand characters)
        overage = len(full_url) - _MAX_URL_LENGTH
        truncated_body = body[: len(body) - overage - len(_TRUNCATION_SUFFIX) - 50] + _TRUNCATION_SUFFIX
        full_url = _make_url(truncated_body)

    return full_url


def _search_issues_via_github_api(search_text: str) -> ExistingIssue | None:
    """Search for existing issues using the GitHub REST API via curl."""
    query = f"{search_text} repo:{GITHUB_REPO} is:issue"
    url = f"https://api.github.com/search/issues?q={quote(query)}&per_page=1"

    result = subprocess.run(
        ["curl", "-s", "-f", "-H", "Accept: application/vnd.github+json", url],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"GitHub API request failed (exit code {result.returncode})")

    data = json.loads(result.stdout)
    items = data.get("items", [])

    if not items:
        return None

    item = items[0]
    return ExistingIssue(
        number=item["number"],
        title=item["title"],
        url=item["html_url"],
    )


def _search_issues_via_gh_cli(search_text: str) -> ExistingIssue | None:
    """Search for existing issues using the gh CLI (works for private repos)."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            GITHUB_REPO,
            "--search",
            search_text,
            "--json",
            "number,title,url",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"gh CLI search failed (exit code {result.returncode})")

    items = json.loads(result.stdout)

    if not items:
        return None

    item = items[0]
    return ExistingIssue(
        number=item["number"],
        title=item["title"],
        url=item["url"],
    )


def search_for_existing_issue(search_text: str) -> ExistingIssue | None:
    """Search for an existing GitHub issue matching the error message."""
    try:
        return _search_issues_via_github_api(search_text)
    except Exception:
        logger.debug("GitHub API search failed, falling back to gh CLI")

    try:
        return _search_issues_via_gh_cli(search_text)
    except Exception:
        logger.debug("gh CLI search also failed")

    return None


def handle_not_implemented_error(error: NotImplementedError) -> None:
    """Handle a NotImplementedError by showing the error and optionally reporting it."""
    error_message = str(error) if str(error) else "Feature not implemented"

    # Always show the error message
    click.echo(f"Error: {error_message}", err=True)

    # In non-interactive mode, just exit
    if not sys.stdin.isatty():
        raise SystemExit(1)

    # In interactive mode, offer to report
    click.echo("")
    if not click.confirm("Would you like to report this as a GitHub issue?", default=True):
        raise SystemExit(1)

    # Search for existing issue
    click.echo("Searching for existing issues...")
    title = build_issue_title(error_message)
    existing = search_for_existing_issue(error_message)

    if existing is not None:
        click.echo(f"Found existing issue #{existing.number}: {existing.title}")
        click.echo(f"Opening: {existing.url}")
        webbrowser.open(existing.url)
    else:
        click.echo("No existing issue found. Opening new issue form...")
        body = build_issue_body(error_message)
        url = build_new_issue_url(title, body)
        webbrowser.open(url)

    raise SystemExit(1)
