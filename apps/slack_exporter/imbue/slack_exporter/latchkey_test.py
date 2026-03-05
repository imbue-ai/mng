from imbue.slack_exporter.errors import SlackApiError
from imbue.slack_exporter.latchkey import extract_next_cursor


def test_extract_next_cursor_returns_cursor_when_present() -> None:
    data = {"response_metadata": {"next_cursor": "abc123"}}
    assert extract_next_cursor(data) == "abc123"


def test_extract_next_cursor_returns_none_when_empty() -> None:
    data = {"response_metadata": {"next_cursor": ""}}
    assert extract_next_cursor(data) is None


def test_extract_next_cursor_returns_none_when_missing_metadata() -> None:
    data: dict[str, object] = {"ok": True}
    assert extract_next_cursor(data) is None


def test_extract_next_cursor_returns_none_when_metadata_is_not_dict() -> None:
    data: dict[str, object] = {"response_metadata": "not a dict"}
    assert extract_next_cursor(data) is None


def test_slack_api_error_has_method_and_error() -> None:
    error = SlackApiError(method="conversations.list", error="invalid_auth")
    assert error.method == "conversations.list"
    assert error.error == "invalid_auth"
    assert "invalid_auth" in str(error)
