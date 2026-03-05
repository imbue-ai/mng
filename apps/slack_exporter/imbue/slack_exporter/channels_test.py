import pytest

from imbue.slack_exporter.channels import resolve_channel_id
from imbue.slack_exporter.errors import ChannelNotFoundError
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.testing import make_stored_channel_info


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
