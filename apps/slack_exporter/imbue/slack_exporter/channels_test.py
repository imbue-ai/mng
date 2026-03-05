from datetime import datetime
from datetime import timezone

import pytest

from imbue.slack_exporter.channels import resolve_channel_id
from imbue.slack_exporter.data_types import StoredChannelInfo
from imbue.slack_exporter.errors import ChannelNotFoundError
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_channel_info(channel_id: str, channel_name: str) -> StoredChannelInfo:
    return StoredChannelInfo(
        channel_id=SlackChannelId(channel_id),
        channel_name=SlackChannelName(channel_name),
        fetched_at=_NOW,
        raw={"id": channel_id, "name": channel_name},
    )


class TestResolveChannelId:
    def test_finds_channel_in_fresh_info(self) -> None:
        info = [_make_channel_info("C123", "general")]
        result = resolve_channel_id(SlackChannelName("general"), info, {})
        assert result == SlackChannelId("C123")

    def test_falls_back_to_cached_mapping(self) -> None:
        cached = {SlackChannelName("general"): SlackChannelId("C999")}
        result = resolve_channel_id(SlackChannelName("general"), [], cached)
        assert result == SlackChannelId("C999")

    def test_prefers_fresh_info_over_cache(self) -> None:
        info = [_make_channel_info("C123", "general")]
        cached = {SlackChannelName("general"): SlackChannelId("C999")}
        result = resolve_channel_id(SlackChannelName("general"), info, cached)
        assert result == SlackChannelId("C123")

    def test_raises_when_channel_not_found(self) -> None:
        with pytest.raises(ChannelNotFoundError):
            resolve_channel_id(SlackChannelName("nonexistent"), [], {})
