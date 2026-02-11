import json
import sys
import webbrowser
from typing import Final
from typing import NoReturn
from urllib.parse import quote
from urllib.parse import urlencode

import click
from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.errors import ConcurrencyGroupError
from imbue.concurrency_group.errors import ProcessSetupError
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.errors import BaseMngrError

GITHUB_REPO: Final[str] = "imbue-ai/mngr"
GITHUB_BASE_URL: Final[str] = f"https://github.com/{GITHUB_REPO}"
ISSUE_TITLE_PREFIX: Final[str] = "[NotImplemented]"

# Maximum URL length to stay within browser and GitHub limits
_MAX_URL_LENGTH: Final[int] = 8000

_TRUNCATION_SUFFIX: Final[str] = "\n\n_(truncated)_"


class IssueSearchError(BaseMngrError):
    """Raised when searching for GitHub issues fails."""


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


@pure
def _make_issue_url(title: str, body: str) -> str:
    """Build a full GitHub new-issue URL from title and body."""
    params = urlencode({"title": title, "body": body}, quote_via=quote)
    return f"{GITHUB_BASE_URL}/issues/new?{params}"


@pure
def build_new_issue_url(title: str, body: str) -> str:
    """Build a GitHub URL for creating a new issue with pre-populated fields."""
    full_url = _make_issue_url(title, body)

    # Truncate body if URL exceeds max length
    if len(full_url) > _MAX_URL_LENGTH:
        # Over-estimate how much to trim (URL encoding can expand characters)
        overage = len(full_url) - _MAX_URL_LENGTH
        truncated_body = body[: len(body) - overage - len(_TRUNCATION_SUFFIX) - 50] + _TRUNCATION_SUFFIX
        full_url = _make_issue_url(title, truncated_body)

    return full_url


def _search_issues_via_github_api(search_text: str, cg: ConcurrencyGroup) -> ExistingIssue | None:
    """Search for existing issues using the GitHub REST API via curl."""
    query = f"{search_text} repo:{GITHUB_REPO} is:issue"
    url = f"https://api.github.com/search/issues?q={quote(query)}&per_page=1"

    try:
        result = cg.run_process_to_completion(
            ["curl", "-s", "-f", "-H", "Accept: application/vnd.github+json", url],
            timeout=10,
            is_checked_after=False,
        )
    except (ProcessSetupError, ConcurrencyGroupError) as e:
        raise IssueSearchError(f"GitHub API request failed: {e}") from e

    if result.returncode != 0:
        raise IssueSearchError(f"GitHub API request failed (exit code {result.returncode})")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise IssueSearchError(f"Failed to parse GitHub API response: {e}") from e

    items = data.get("items", [])

    if not items:
        return None

    item = items[0]
    return ExistingIssue(
        number=item["number"],
        title=item["title"],
        url=item["html_url"],
    )


def _search_issues_via_gh_cli(search_text: str, cg: ConcurrencyGroup) -> ExistingIssue | None:
    """Search for existing issues using the gh CLI (works for private repos)."""
    try:
        result = cg.run_process_to_completion(
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
            timeout=10,
            is_checked_after=False,
        )
    except (ProcessSetupError, ConcurrencyGroupError) as e:
        raise IssueSearchError(f"gh CLI search failed: {e}") from e

    if result.returncode != 0:
        raise IssueSearchError(f"gh CLI search failed (exit code {result.returncode})")

    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise IssueSearchError(f"Failed to parse gh CLI response: {e}") from e

    if not items:
        return None

    item = items[0]
    return ExistingIssue(
        number=item["number"],
        title=item["title"],
        url=item["url"],
    )


def search_for_existing_issue(search_text: str, cg: ConcurrencyGroup) -> ExistingIssue | None:
    """Search for an existing GitHub issue matching the error message."""
    try:
        return _search_issues_via_github_api(search_text, cg)
    except IssueSearchError:
        logger.debug("GitHub API search failed, falling back to gh CLI")

    try:
        return _search_issues_via_gh_cli(search_text, cg)
    except IssueSearchError:
        logger.debug("gh CLI search also failed")

    return None


def _format_existing_issue_message(issue: ExistingIssue) -> str:
    return "Found existing issue " + str(issue.number) + ": " + issue.title


def handle_not_implemented_error(error: NotImplementedError) -> NoReturn:
    """Handle a NotImplementedError by showing the error and optionally reporting it."""
    error_message = str(error) if str(error) else "Feature not implemented"

    # Always show the error message
    logger.error("Error: {}", error_message)

    # In non-interactive mode, just exit
    if not sys.stdin.isatty():
        raise SystemExit(1)

    # In interactive mode, offer to report
    if not click.confirm("\nWould you like to report this as a GitHub issue?", default=True):
        raise SystemExit(1)

    # Search for existing issue using a standalone ConcurrencyGroup
    logger.info("Searching for existing issues...")
    title = build_issue_title(error_message)
    with ConcurrencyGroup(name="issue-search") as cg:
        existing = search_for_existing_issue(error_message, cg)

    if existing is not None:
        logger.info("{}", _format_existing_issue_message(existing))
        logger.info("Opening: {}", existing.url)
        webbrowser.open(existing.url)
    else:
        logger.info("No existing issue found. Opening new issue form...")
        body = build_issue_body(error_message)
        url = build_new_issue_url(title, body)
        webbrowser.open(url)

    raise SystemExit(1)
