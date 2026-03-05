import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from imbue.slack_exporter.data_types import ChannelConfig
from imbue.slack_exporter.data_types import ExporterSettings
from imbue.slack_exporter.data_types import SlackApiCaller
from imbue.slack_exporter.exporter import _datetime_to_slack_timestamp
from imbue.slack_exporter.exporter import _fetch_all_messages_for_channel
from imbue.slack_exporter.exporter import run_export
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.primitives import SlackMessageTimestamp
from imbue.slack_exporter.testing import make_stored_message


def _make_fake_api_caller(
    response_by_method: dict[str, list[dict[str, Any]]],
) -> SlackApiCaller:
    """Create a fake SlackApiCaller that returns pre-configured responses per method.

    Each method maps to a list of responses that are returned in order (for pagination).
    """
    call_index_by_method: dict[str, int] = {}

    def fake_api_caller(method: str, query_params: dict[str, str] | None = None) -> dict[str, Any]:
        responses = response_by_method.get(method, [])
        idx = call_index_by_method.get(method, 0)
        call_index_by_method[method] = idx + 1
        return responses[idx]

    return fake_api_caller


def _history_response(
    messages: list[dict[str, str]],
    has_more: bool = False,
    next_cursor: str = "",
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": True,
        "messages": messages,
        "has_more": has_more,
    }
    if next_cursor:
        response["response_metadata"] = {"next_cursor": next_cursor}
    return response


def _channel_list_response(channels: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "ok": True,
        "channels": channels,
        "response_metadata": {"next_cursor": ""},
    }


def test_datetime_to_slack_timestamp_converts_correctly() -> None:
    dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = _datetime_to_slack_timestamp(dt)
    assert result == SlackMessageTimestamp("1704067200.000000")


def test_datetime_to_slack_timestamp_preserves_fractional_seconds() -> None:
    dt = datetime(2024, 6, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
    result = _datetime_to_slack_timestamp(dt)
    assert "." in result


def test_fetch_all_messages_fetches_single_page() -> None:
    api_caller = _make_fake_api_caller(
        {
            "conversations.history": [
                _history_response(messages=[{"ts": "1700000000.000001", "text": "hello"}]),
            ],
        }
    )

    messages = _fetch_all_messages_for_channel(
        channel_id=SlackChannelId("C123"),
        channel_name=SlackChannelName("general"),
        oldest_ts=SlackMessageTimestamp("1699999999.000000"),
        is_inclusive=True,
        api_caller=api_caller,
    )

    assert len(messages) == 1
    assert messages[0].timestamp == SlackMessageTimestamp("1700000000.000001")
    assert messages[0].channel_id == SlackChannelId("C123")


def test_fetch_all_messages_handles_pagination() -> None:
    api_caller = _make_fake_api_caller(
        {
            "conversations.history": [
                _history_response(
                    messages=[{"ts": "1700000000.000001", "text": "first"}],
                    has_more=True,
                    next_cursor="cursor_abc",
                ),
                _history_response(messages=[{"ts": "1700000000.000002", "text": "second"}]),
            ],
        }
    )

    messages = _fetch_all_messages_for_channel(
        channel_id=SlackChannelId("C123"),
        channel_name=SlackChannelName("general"),
        oldest_ts=SlackMessageTimestamp("1699999999.000000"),
        is_inclusive=True,
        api_caller=api_caller,
    )

    assert len(messages) == 2


def test_fetch_all_messages_skips_messages_without_ts() -> None:
    api_caller = _make_fake_api_caller(
        {
            "conversations.history": [
                _history_response(messages=[{"text": "no timestamp"}, {"ts": "1700000000.000001", "text": "has ts"}]),
            ],
        }
    )

    messages = _fetch_all_messages_for_channel(
        channel_id=SlackChannelId("C123"),
        channel_name=SlackChannelName("general"),
        oldest_ts=SlackMessageTimestamp("1699999999.000000"),
        is_inclusive=True,
        api_caller=api_caller,
    )

    assert len(messages) == 1


def test_fetch_all_messages_returns_empty_when_no_messages() -> None:
    api_caller = _make_fake_api_caller(
        {
            "conversations.history": [_history_response(messages=[])],
        }
    )

    messages = _fetch_all_messages_for_channel(
        channel_id=SlackChannelId("C123"),
        channel_name=SlackChannelName("general"),
        oldest_ts=SlackMessageTimestamp("1699999999.000000"),
        is_inclusive=True,
        api_caller=api_caller,
    )

    assert messages == []


def test_run_export_writes_messages_to_file(temp_output_path: Path) -> None:
    api_caller = _make_fake_api_caller(
        {
            "conversations.list": [
                _channel_list_response(channels=[{"id": "C123", "name": "general"}]),
            ],
            "conversations.history": [
                _history_response(messages=[{"ts": "1700000000.000001", "text": "hello"}]),
            ],
        }
    )

    settings = ExporterSettings(
        channels=(ChannelConfig(name=SlackChannelName("general")),),
        default_oldest=datetime(2024, 1, 1, tzinfo=timezone.utc),
        output_path=temp_output_path,
    )

    run_export(settings, api_caller=api_caller)

    lines = temp_output_path.read_text().strip().splitlines()
    assert len(lines) >= 2

    message_lines = [json.loads(line) for line in lines if json.loads(line).get("kind") == "MESSAGE"]
    assert len(message_lines) == 1
    assert message_lines[0]["channel_id"] == "C123"


def test_run_export_incremental_resumes_from_latest(temp_output_path: Path) -> None:
    existing_msg = make_stored_message(ts="1700000000.000001")
    temp_output_path.write_text(existing_msg.model_dump_json() + "\n")

    captured_params: list[dict[str, str] | None] = []

    def tracking_api_caller(method: str, query_params: dict[str, str] | None = None) -> dict[str, Any]:
        if method == "conversations.list":
            return _channel_list_response(channels=[{"id": "C123", "name": "general"}])
        elif method == "conversations.history":
            captured_params.append(query_params)
            return _history_response(messages=[{"ts": "1700000000.000009", "text": "new"}])
        else:
            return {"ok": True}

    settings = ExporterSettings(
        channels=(ChannelConfig(name=SlackChannelName("general")),),
        default_oldest=datetime(2024, 1, 1, tzinfo=timezone.utc),
        output_path=temp_output_path,
    )

    run_export(settings, api_caller=tracking_api_caller)

    # Verify incremental behavior
    assert len(captured_params) == 1
    assert captured_params[0] is not None
    assert captured_params[0].get("oldest") == "1700000000.000001"
    assert captured_params[0].get("inclusive") == "false"

    lines = temp_output_path.read_text().strip().splitlines()
    assert len(lines) >= 3
