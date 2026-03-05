from datetime import datetime
from datetime import timezone

from imbue.slack_exporter.main import _parse_channel_spec
from imbue.slack_exporter.primitives import SlackChannelName


class TestParseChannelSpec:
    def test_simple_name(self) -> None:
        config = _parse_channel_spec("general")
        assert config.name == SlackChannelName("general")
        assert config.oldest is None

    def test_name_with_hash(self) -> None:
        config = _parse_channel_spec("#general")
        assert config.name == SlackChannelName("general")

    def test_name_with_date(self) -> None:
        config = _parse_channel_spec("general:2024-06-15")
        assert config.name == SlackChannelName("general")
        assert config.oldest == datetime(2024, 6, 15, tzinfo=timezone.utc)

    def test_name_with_datetime(self) -> None:
        config = _parse_channel_spec("random:2024-06-15T10:30:00")
        assert config.name == SlackChannelName("random")
        assert config.oldest == datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
