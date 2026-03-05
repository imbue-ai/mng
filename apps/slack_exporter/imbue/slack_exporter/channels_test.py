from typing import Any

import pytest

from imbue.slack_exporter.channels import fetch_channel_list
from imbue.slack_exporter.channels import resolve_channel_id
from imbue.slack_exporter.data_types import SlackApiCaller
from imbue.slack_exporter.errors import ChannelNotFoundError
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.testing import make_stored_channel_info


def _make_channel_list_api_caller(pages: list[dict[str, Any]]) -> SlackApiCaller:
    """Create a fake api caller that returns channel list pages in order."""
    call_idx = 0

    def fake_caller(method: str, query_params: dict[str, str] | None = None) -> dict[str, Any]:
        nonlocal call_idx
        result = pages[call_idx]
        call_idx += 1
        return result

    return fake_caller


def test_fetch_channel_list_single_page() -> None:
    api_caller = _make_channel_list_api_caller(
        [
            {
                "ok": True,
                "channels": [
                    {"id": "C123", "name": "general"},
                    {"id": "C456", "name": "random"},
                ],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )

    channels = fetch_channel_list(api_caller)

    assert len(channels) == 2
    assert channels[0].channel_id == SlackChannelId("C123")
    assert channels[0].channel_name == SlackChannelName("general")
    assert channels[1].channel_id == SlackChannelId("C456")


def test_fetch_channel_list_multiple_pages() -> None:
    api_caller = _make_channel_list_api_caller(
        [
            {
                "ok": True,
                "channels": [{"id": "C123", "name": "general"}],
                "response_metadata": {"next_cursor": "cursor_page2"},
            },
            {
                "ok": True,
                "channels": [{"id": "C456", "name": "random"}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )

    channels = fetch_channel_list(api_caller)

    assert len(channels) == 2
    assert channels[0].channel_id == SlackChannelId("C123")
    assert channels[1].channel_id == SlackChannelId("C456")


def test_fetch_channel_list_empty_response() -> None:
    api_caller = _make_channel_list_api_caller(
        [
            {
                "ok": True,
                "channels": [],
                "response_metadata": {"next_cursor": ""},
            },
        ]
    )

    channels = fetch_channel_list(api_caller)
    assert channels == []


def test_resolve_channel_id_finds_channel_in_fresh_info() -> None:
    info = [make_stored_channel_info("C123", "general")]
    result = resolve_channel_id(SlackChannelName("general"), info, {})
    assert result == SlackChannelId("C123")


def test_resolve_channel_id_falls_back_to_cached_mapping() -> None:
    cached = {SlackChannelName("general"): SlackChannelId("C999")}
    result = resolve_channel_id(SlackChannelName("general"), [], cached)
    assert result == SlackChannelId("C999")


def test_resolve_channel_id_prefers_fresh_info_over_cache() -> None:
    info = [make_stored_channel_info("C123", "general")]
    cached = {SlackChannelName("general"): SlackChannelId("C999")}
    result = resolve_channel_id(SlackChannelName("general"), info, cached)
    assert result == SlackChannelId("C123")


def test_resolve_channel_id_raises_when_channel_not_found() -> None:
    with pytest.raises(ChannelNotFoundError):
        resolve_channel_id(SlackChannelName("nonexistent"), [], {})
