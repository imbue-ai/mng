"""Unit tests for load_triaged_issues.py."""

from typing import Any

from scripts.load_triaged_issues import GitHubComment
from scripts.load_triaged_issues import GitHubIssue
from scripts.load_triaged_issues import TriagedIssuesOutput
from scripts.load_triaged_issues import create_github_issue
from scripts.load_triaged_issues import filter_comments_by_authorized_users


def test_filter_comments_by_authorized_users_filters_to_authorized_only() -> None:
    """Test that only comments from authorized users are included."""
    comments = [
        {"author": {"login": "alice"}, "body": "Comment from alice", "createdAt": "2026-01-01T00:00:00Z"},
        {"author": {"login": "bob"}, "body": "Comment from bob", "createdAt": "2026-01-02T00:00:00Z"},
        {"author": {"login": "charlie"}, "body": "Comment from charlie", "createdAt": "2026-01-03T00:00:00Z"},
    ]
    authorized_users = ("alice", "charlie")

    result = filter_comments_by_authorized_users(comments, authorized_users)

    assert len(result) == 2
    assert result[0].author == "alice"
    assert result[0].body == "Comment from alice"
    assert result[1].author == "charlie"
    assert result[1].body == "Comment from charlie"


def test_filter_comments_by_authorized_users_returns_empty_when_no_matches() -> None:
    """Test that empty tuple is returned when no authorized users commented."""
    comments = [
        {"author": {"login": "bob"}, "body": "Comment from bob", "createdAt": "2026-01-01T00:00:00Z"},
    ]
    authorized_users = ("alice",)

    result = filter_comments_by_authorized_users(comments, authorized_users)

    assert len(result) == 0


def test_filter_comments_by_authorized_users_handles_empty_comments() -> None:
    """Test that empty tuple is returned for empty comment list."""
    comments: list[dict[str, Any]] = []
    authorized_users = ("alice",)

    result = filter_comments_by_authorized_users(comments, authorized_users)

    assert len(result) == 0


def test_filter_comments_by_authorized_users_handles_missing_author() -> None:
    """Test that comments with missing author are skipped."""
    comments = [
        {"author": {}, "body": "Comment with no login", "createdAt": "2026-01-01T00:00:00Z"},
        {"author": {"login": "alice"}, "body": "Comment from alice", "createdAt": "2026-01-02T00:00:00Z"},
    ]
    authorized_users = ("alice",)

    result = filter_comments_by_authorized_users(comments, authorized_users)

    assert len(result) == 1
    assert result[0].author == "alice"


def test_create_github_issue_creates_issue_with_correct_fields() -> None:
    """Test that create_github_issue correctly maps raw API data."""
    raw_issue = {
        "number": 42,
        "title": "Test issue title",
        "body": "Test issue body",
        "labels": [{"name": "bug"}, {"name": "autoclaude"}],
        "createdAt": "2026-01-01T00:00:00Z",
        "url": "https://github.com/test/repo/issues/42",
    }
    authorized_comments = (GitHubComment(author="alice", body="LGTM", created_at="2026-01-02T00:00:00Z"),)

    result = create_github_issue(raw_issue, authorized_comments)

    assert result.number == 42
    assert result.title == "Test issue title"
    assert result.body == "Test issue body"
    assert result.labels == ("bug", "autoclaude")
    assert result.created_at == "2026-01-01T00:00:00Z"
    assert result.url == "https://github.com/test/repo/issues/42"
    assert len(result.authorized_comments) == 1
    assert result.authorized_comments[0].author == "alice"


def test_create_github_issue_handles_missing_fields() -> None:
    """Test that create_github_issue handles missing optional fields."""
    raw_issue = {
        "number": 1,
    }
    authorized_comments: tuple[GitHubComment, ...] = ()

    result = create_github_issue(raw_issue, authorized_comments)

    assert result.number == 1
    assert result.title == ""
    assert result.body == ""
    assert result.labels == ()
    assert result.created_at == ""
    assert result.url == ""
    assert len(result.authorized_comments) == 0


def test_create_github_issue_handles_labels_as_strings() -> None:
    """Test that create_github_issue handles labels that are strings instead of dicts."""
    raw_issue = {
        "number": 1,
        "title": "Test",
        "body": "Body",
        "labels": ["label1", "label2"],
        "createdAt": "2026-01-01T00:00:00Z",
        "url": "https://example.com",
    }
    authorized_comments: tuple[GitHubComment, ...] = ()

    result = create_github_issue(raw_issue, authorized_comments)

    assert result.labels == ("label1", "label2")


def test_github_comment_model_serialization() -> None:
    """Test that GitHubComment can be serialized and deserialized."""
    comment = GitHubComment(
        author="alice",
        body="Test comment",
        created_at="2026-01-01T00:00:00Z",
    )

    serialized = comment.model_dump()

    assert serialized["author"] == "alice"
    assert serialized["body"] == "Test comment"
    assert serialized["created_at"] == "2026-01-01T00:00:00Z"


def test_github_issue_model_serialization() -> None:
    """Test that GitHubIssue can be serialized and deserialized."""
    issue = GitHubIssue(
        number=42,
        title="Test",
        body="Body",
        labels=("bug",),
        created_at="2026-01-01T00:00:00Z",
        url="https://example.com",
        authorized_comments=(),
    )

    serialized = issue.model_dump()

    assert serialized["number"] == 42
    assert serialized["title"] == "Test"
    assert serialized["labels"] == ("bug",)


def test_triaged_issues_output_serializes_to_json() -> None:
    """Test that TriagedIssuesOutput serializes to JSON correctly."""
    output = TriagedIssuesOutput(issues=())

    json_str = output.model_dump_json()

    assert '"issues":[]' in json_str or '"issues": []' in json_str


def test_triaged_issues_output_with_issues() -> None:
    """Test TriagedIssuesOutput with actual issues."""
    issue = GitHubIssue(
        number=1,
        title="Test",
        body="Body",
        labels=(),
        created_at="2026-01-01T00:00:00Z",
        url="https://example.com",
        authorized_comments=(),
    )
    output = TriagedIssuesOutput(issues=(issue,))

    json_str = output.model_dump_json()

    assert '"number":1' in json_str or '"number": 1' in json_str
    assert '"title":"Test"' in json_str or '"title": "Test"' in json_str
