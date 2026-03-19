import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from io import StringIO
from typing import Any

from imbue.slack_exporter.channels import fetch_raw_channel_list
from imbue.slack_exporter.data_types import SlackApiCaller
from imbue.slack_exporter.latchkey import call_slack_api

logger = logging.getLogger(__name__)


def _format_timestamp(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


def _fetch_latest_message_timestamps(
    api_caller: SlackApiCaller,
    channels: list[dict[str, Any]],
) -> dict[str, float]:
    """Fetch the latest message timestamp per channel via conversations.info."""
    latest_by_channel_id: dict[str, float] = {}
    total_channels = len(channels)
    for channel_idx, channel in enumerate(channels):
        channel_id = channel["id"]
        if total_channels > 1:
            logger.info("Fetching channel info %d/%d: %s", channel_idx + 1, total_channels, channel.get("name", "?"))
        data = api_caller("conversations.info", {"channel": channel_id})
        channel_info = data.get("channel", {})
        latest = channel_info.get("latest")
        if isinstance(latest, dict) and latest.get("ts"):
            latest_by_channel_id[channel_id] = float(latest["ts"])
    return latest_by_channel_id


def fetch_and_sort_channels(
    api_caller: SlackApiCaller,
    members_only: bool,
) -> list[dict[str, Any]]:
    """Fetch channels and sort by most recent message activity."""
    raw_channels = fetch_raw_channel_list(api_caller=api_caller, members_only=members_only)

    # Fetch actual latest message timestamps via conversations.info
    latest_by_id = _fetch_latest_message_timestamps(api_caller, raw_channels)

    # Annotate each channel with its latest message timestamp for display
    for channel in raw_channels:
        channel["_latest_message_ts"] = latest_by_id.get(channel["id"], 0.0)

    return sorted(raw_channels, key=lambda ch: ch["_latest_message_ts"], reverse=True)


def format_channel_table(channels: Sequence[dict[str, Any]]) -> str:
    """Format channels as a table string."""
    buf = StringIO()
    if not channels:
        buf.write("No channels found.\n")
        return buf.getvalue()

    buf.write(f"{'#':<4} {'CHANNEL':<30} {'LAST MESSAGE':<18}\n")
    buf.write("-" * 52 + "\n")

    for idx, channel in enumerate(channels):
        name = channel.get("name", "unknown")
        latest_ts = channel.get("_latest_message_ts", 0.0)
        ts_str = _format_timestamp(latest_ts) if latest_ts > 0 else "no messages"
        buf.write(f"{idx + 1:<4} {name:<30} {ts_str:<18}\n")

    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List Slack channels sorted by most recent message activity",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_channels",
        help="Include channels you're not a member of (default: only member channels)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sorted_channels = fetch_and_sort_channels(
        api_caller=call_slack_api,
        members_only=not args.all_channels,
    )
    sys.stdout.write(format_channel_table(sorted_channels))


if __name__ == "__main__":
    main()
