import logging
from datetime import datetime
from datetime import timezone
from typing import Any

from imbue.slack_exporter.channels import fetch_channel_list
from imbue.slack_exporter.channels import resolve_channel_id
from imbue.slack_exporter.data_types import ChannelConfig
from imbue.slack_exporter.data_types import ChannelExportState
from imbue.slack_exporter.data_types import ExporterSettings
from imbue.slack_exporter.data_types import StoredChannelInfo
from imbue.slack_exporter.data_types import StoredMessage
from imbue.slack_exporter.latchkey import call_slack_api
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.primitives import SlackMessageTimestamp
from imbue.slack_exporter.store import append_records
from imbue.slack_exporter.store import load_existing_state

logger = logging.getLogger(__name__)


def run_export(settings: ExporterSettings) -> None:
    """Run the full export process: load state, resolve channels, fetch new messages, save."""
    state_by_channel_id, cached_channel_id_by_name = load_existing_state(settings.output_path)

    # Fetch the channel list from Slack and persist it
    channel_info_records = fetch_channel_list()
    append_records(settings.output_path, channel_info_records)

    # Update the cached name-to-id mapping with fresh data
    for info in channel_info_records:
        cached_channel_id_by_name[info.channel_name] = info.channel_id

    # Export each configured channel
    for channel_config in settings.channels:
        _export_single_channel(
            channel_config=channel_config,
            channel_info_records=channel_info_records,
            cached_channel_id_by_name=cached_channel_id_by_name,
            state_by_channel_id=state_by_channel_id,
            settings=settings,
        )


def _export_single_channel(
    channel_config: ChannelConfig,
    channel_info_records: list[StoredChannelInfo],
    cached_channel_id_by_name: dict[SlackChannelName, SlackChannelId],
    state_by_channel_id: dict[SlackChannelId, ChannelExportState],
    settings: ExporterSettings,
) -> None:
    """Export messages from a single channel."""
    channel_id = resolve_channel_id(
        channel_config.name,
        channel_info_records,
        cached_channel_id_by_name,
    )
    logger.info("Exporting #%s (ID: %s)", channel_config.name, channel_id)

    existing_state = state_by_channel_id.get(channel_id)

    # Determine the oldest timestamp to fetch from
    oldest_datetime = channel_config.oldest or settings.default_oldest
    oldest_ts = _datetime_to_slack_timestamp(oldest_datetime)

    # If we already have messages, fetch only newer ones
    if existing_state and existing_state.latest_message_timestamp:
        oldest_ts = existing_state.latest_message_timestamp
        logger.info(
            "  Resuming from timestamp %s for #%s",
            oldest_ts,
            channel_config.name,
        )

    all_new_messages = _fetch_all_messages_for_channel(
        channel_id=channel_id,
        channel_name=channel_config.name,
        oldest_ts=oldest_ts,
        # When resuming, we already have the message at oldest_ts, so exclude it
        is_inclusive=existing_state is None or existing_state.latest_message_timestamp is None,
    )

    if all_new_messages:
        append_records(settings.output_path, all_new_messages)
        logger.info("  Saved %d new messages from #%s", len(all_new_messages), channel_config.name)
    else:
        logger.info("  No new messages in #%s", channel_config.name)


def _fetch_all_messages_for_channel(
    channel_id: SlackChannelId,
    channel_name: SlackChannelName,
    oldest_ts: SlackMessageTimestamp,
    is_inclusive: bool,
) -> list[StoredMessage]:
    """Fetch all messages from a channel newer than oldest_ts, handling pagination."""
    all_messages: list[StoredMessage] = []
    cursor: str | None = None
    now = datetime.now(timezone.utc)

    while True:
        params: dict[str, str] = {
            "channel": channel_id,
            "oldest": oldest_ts,
            "inclusive": "true" if is_inclusive else "false",
            "include_all_metadata": "true",
            "limit": "200",
        }
        if cursor:
            params["cursor"] = cursor

        data = call_slack_api("conversations.history", query_params=params)

        for message_raw in data.get("messages", []):
            ts = message_raw.get("ts", "")
            if not ts:
                continue
            stored_message = StoredMessage(
                channel_id=channel_id,
                channel_name=channel_name,
                timestamp=SlackMessageTimestamp(ts),
                fetched_at=now,
                raw=message_raw,
            )
            all_messages.append(stored_message)

        if not data.get("has_more", False):
            break

        next_cursor = _extract_response_cursor(data)
        if not next_cursor:
            break
        cursor = next_cursor

    return all_messages


def _datetime_to_slack_timestamp(dt: datetime) -> SlackMessageTimestamp:
    """Convert a datetime to a Slack-style timestamp string."""
    return SlackMessageTimestamp(f"{dt.timestamp():.6f}")


def _extract_response_cursor(data: dict[str, Any]) -> str | None:
    """Extract the pagination cursor from a Slack API response."""
    response_metadata = data.get("response_metadata")
    if not isinstance(response_metadata, dict):
        return None
    next_cursor = response_metadata.get("next_cursor", "")
    if not next_cursor:
        return None
    return next_cursor
