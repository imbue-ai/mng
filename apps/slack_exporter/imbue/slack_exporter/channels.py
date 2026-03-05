import logging
from typing import Any

from imbue.imbue_common.event_envelope import EventSource
from imbue.imbue_common.event_envelope import EventType
from imbue.slack_exporter.data_types import ChannelEvent
from imbue.slack_exporter.data_types import SlackApiCaller
from imbue.slack_exporter.data_types import UserEvent
from imbue.slack_exporter.data_types import make_event_id
from imbue.slack_exporter.data_types import make_iso_timestamp
from imbue.slack_exporter.errors import ChannelNotFoundError
from imbue.slack_exporter.latchkey import extract_next_cursor
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.primitives import SlackUserId

logger = logging.getLogger(__name__)

_CHANNEL_SOURCE = EventSource("channels")
_USER_SOURCE = EventSource("users")


def fetch_channel_list(api_caller: SlackApiCaller) -> list[ChannelEvent]:
    """Fetch all non-archived channels from Slack."""
    all_channels: list[ChannelEvent] = []
    cursor: str | None = None

    while True:
        params: dict[str, str] = {
            "exclude_archived": "true",
            "limit": "200",
            "types": "public_channel,private_channel",
        }
        if cursor:
            params["cursor"] = cursor

        data = api_caller("conversations.list", params)

        for channel_raw in data.get("channels", []):
            event = _make_channel_event(channel_raw, event_type=EventType("channel_fetched"))
            all_channels.append(event)

        next_cursor = extract_next_cursor(data)
        if not next_cursor:
            break
        cursor = next_cursor

    logger.info("Fetched %d channels from Slack", len(all_channels))
    return all_channels


def fetch_user_list(api_caller: SlackApiCaller) -> list[UserEvent]:
    """Fetch all users from Slack."""
    all_users: list[UserEvent] = []
    cursor: str | None = None

    while True:
        params: dict[str, str] = {"limit": "200"}
        if cursor:
            params["cursor"] = cursor

        data = api_caller("users.list", params)

        for user_raw in data.get("members", []):
            event = _make_user_event(user_raw, event_type=EventType("user_fetched"))
            all_users.append(event)

        next_cursor = extract_next_cursor(data)
        if not next_cursor:
            break
        cursor = next_cursor

    logger.info("Fetched %d users from Slack", len(all_users))
    return all_users


def resolve_channel_id(
    channel_name: SlackChannelName,
    channel_events: list[ChannelEvent],
    cached_channel_id_by_name: dict[SlackChannelName, SlackChannelId],
) -> SlackChannelId:
    """Resolve a channel name to its ID, using fetched events or cached mappings.

    Raises ChannelNotFoundError if the channel cannot be found.
    """
    for event in channel_events:
        if event.channel_name == channel_name:
            return event.channel_id

    cached_id = cached_channel_id_by_name.get(channel_name)
    if cached_id is not None:
        return cached_id

    raise ChannelNotFoundError(channel_name)


def _make_channel_event(channel_raw: dict[str, Any], event_type: EventType) -> ChannelEvent:
    return ChannelEvent(
        timestamp=make_iso_timestamp(),
        type=event_type,
        event_id=make_event_id(),
        source=_CHANNEL_SOURCE,
        channel_id=SlackChannelId(channel_raw["id"]),
        channel_name=SlackChannelName(channel_raw["name"]),
        raw=channel_raw,
    )


def _make_user_event(user_raw: dict[str, Any], event_type: EventType) -> UserEvent:
    return UserEvent(
        timestamp=make_iso_timestamp(),
        type=event_type,
        event_id=make_event_id(),
        source=_USER_SOURCE,
        user_id=SlackUserId(user_raw["id"]),
        raw=user_raw,
    )
