import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from imbue.slack_exporter.data_types import ChannelExportState
from imbue.slack_exporter.data_types import EventKind
from imbue.slack_exporter.data_types import StoredChannelInfo
from imbue.slack_exporter.data_types import StoredMessage
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.primitives import SlackMessageTimestamp

logger = logging.getLogger(__name__)


def load_existing_state(
    output_path: Path,
) -> tuple[dict[SlackChannelId, ChannelExportState], dict[SlackChannelName, SlackChannelId]]:
    """Load existing JSONL file and derive channel export states and name-to-id mappings.

    Returns a tuple of (state_by_channel_id, channel_id_by_name).
    """
    state_by_channel_id: dict[SlackChannelId, ChannelExportState] = {}
    channel_id_by_name: dict[SlackChannelName, SlackChannelId] = {}

    if not output_path.exists():
        logger.info("No existing export file at %s, starting fresh", output_path)
        return state_by_channel_id, channel_id_by_name

    line_count = 0
    message_count = 0
    channel_info_count = 0

    for line in output_path.read_text().splitlines():
        line_count += 1
        if not line.strip():
            continue

        try:
            record: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSON on line %d", line_count)
            continue

        kind = record.get("kind")
        if kind == EventKind.CHANNEL_INFO:
            channel_info_count += 1
            info = StoredChannelInfo.model_validate(record)
            channel_id_by_name[info.channel_name] = info.channel_id
        elif kind == EventKind.MESSAGE:
            message_count += 1
            msg = StoredMessage.model_validate(record)
            channel_id_by_name[msg.channel_name] = msg.channel_id

            existing = state_by_channel_id.get(msg.channel_id)
            if existing is None or existing.latest_message_timestamp is None:
                state_by_channel_id[msg.channel_id] = ChannelExportState(
                    channel_id=msg.channel_id,
                    channel_name=msg.channel_name,
                    latest_message_timestamp=msg.timestamp,
                )
            elif msg.timestamp > existing.latest_message_timestamp:
                state_by_channel_id[msg.channel_id] = ChannelExportState(
                    channel_id=msg.channel_id,
                    channel_name=msg.channel_name,
                    latest_message_timestamp=msg.timestamp,
                )
            else:
                pass

    logger.info(
        "Loaded %d lines (%d messages, %d channel info records) from %s",
        line_count,
        message_count,
        channel_info_count,
        output_path,
    )
    return state_by_channel_id, channel_id_by_name


def append_records(output_path: Path, records: Sequence[StoredMessage | StoredChannelInfo]) -> None:
    """Append records to the JSONL file."""
    if not records:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")

    logger.info("Appended %d records to %s", len(records), output_path)


def _find_latest_timestamp(
    messages: Sequence[StoredMessage],
) -> SlackMessageTimestamp | None:
    """Find the latest message timestamp from a sequence of stored messages."""
    if not messages:
        return None
    return max(msg.timestamp for msg in messages)
