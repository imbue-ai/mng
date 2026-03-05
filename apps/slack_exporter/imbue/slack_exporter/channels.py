import logging
from datetime import datetime
from datetime import timezone
from typing import Any

from imbue.slack_exporter.data_types import StoredChannelInfo
from imbue.slack_exporter.errors import ChannelNotFoundError
from imbue.slack_exporter.latchkey import call_slack_api
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName

logger = logging.getLogger(__name__)


def fetch_channel_list() -> list[StoredChannelInfo]:
    """Fetch all non-archived channels from Slack and return them as StoredChannelInfo records."""
    all_channels: list[StoredChannelInfo] = []
    cursor: str | None = None
    now = datetime.now(timezone.utc)

    while True:
        params: dict[str, str] = {
            "exclude_archived": "true",
            "limit": "200",
            "types": "public_channel,private_channel",
        }
        if cursor:
            params["cursor"] = cursor

        data = call_slack_api("conversations.list", query_params=params)

        for channel_raw in data.get("channels", []):
            channel_info = StoredChannelInfo(
                channel_id=SlackChannelId(channel_raw["id"]),
                channel_name=SlackChannelName(channel_raw["name"]),
                fetched_at=now,
                raw=channel_raw,
            )
            all_channels.append(channel_info)

        next_cursor = _extract_next_cursor(data)
        if not next_cursor:
            break
        cursor = next_cursor

    logger.info("Fetched %d channels from Slack", len(all_channels))
    return all_channels


def resolve_channel_id(
    channel_name: SlackChannelName,
    channel_info_records: list[StoredChannelInfo],
    cached_channel_id_by_name: dict[SlackChannelName, SlackChannelId],
) -> SlackChannelId:
    """Resolve a channel name to its ID, using fetched info or cached mappings.

    Raises ChannelNotFoundError if the channel cannot be found.
    """
    # Check freshly fetched channel info first
    for info in channel_info_records:
        if info.channel_name == channel_name:
            return info.channel_id

    # Fall back to cached mapping
    cached_id = cached_channel_id_by_name.get(channel_name)
    if cached_id is not None:
        return cached_id

    raise ChannelNotFoundError(channel_name)


def _extract_next_cursor(data: dict[str, Any]) -> str | None:
    """Extract the pagination cursor from a Slack API response, if present."""
    response_metadata = data.get("response_metadata")
    if not isinstance(response_metadata, dict):
        return None
    next_cursor = response_metadata.get("next_cursor", "")
    if not next_cursor:
        return None
    return next_cursor
