from imbue.slack_exporter.list_channels import fetch_and_sort_channels
from imbue.slack_exporter.list_channels import format_channel_table
from imbue.slack_exporter.testing import make_fake_api_caller
from imbue.slack_exporter.testing import make_slack_response


def _make_channel_info_response(channel_id: str, latest_ts: str) -> dict:
    return {
        "ok": True,
        "channel": {
            "id": channel_id,
            "latest": {"ts": latest_ts, "text": "hello"},
        },
    }


def test_fetch_and_sort_channels_sorts_by_latest_message() -> None:
    api_caller = make_fake_api_caller(
        {
            "conversations.list": [
                make_slack_response(
                    "channels",
                    [
                        {"id": "C1", "name": "old", "is_member": True},
                        {"id": "C2", "name": "new", "is_member": True},
                        {"id": "C3", "name": "mid", "is_member": True},
                    ],
                ),
            ],
            "conversations.info": [
                _make_channel_info_response("C1", "1000000000.000001"),
                _make_channel_info_response("C2", "1700000000.000001"),
                _make_channel_info_response("C3", "1400000000.000001"),
            ],
        }
    )

    result = fetch_and_sort_channels(api_caller=api_caller, members_only=True)

    assert [ch["name"] for ch in result] == ["new", "mid", "old"]


def test_fetch_and_sort_channels_filters_non_member_channels() -> None:
    api_caller = make_fake_api_caller(
        {
            "conversations.list": [
                make_slack_response(
                    "channels",
                    [
                        {"id": "C1", "name": "member", "is_member": True},
                        {"id": "C2", "name": "not-member", "is_member": False},
                    ],
                ),
            ],
            "conversations.info": [
                _make_channel_info_response("C1", "1700000000.000001"),
            ],
        }
    )

    result = fetch_and_sort_channels(api_caller=api_caller, members_only=True)

    assert len(result) == 1
    assert result[0]["name"] == "member"


def test_fetch_and_sort_channels_includes_all_when_members_only_false() -> None:
    api_caller = make_fake_api_caller(
        {
            "conversations.list": [
                make_slack_response(
                    "channels",
                    [
                        {"id": "C1", "name": "member", "is_member": True},
                        {"id": "C2", "name": "not-member", "is_member": False},
                    ],
                ),
            ],
            "conversations.info": [
                _make_channel_info_response("C1", "1700000000.000001"),
                _make_channel_info_response("C2", "1600000000.000001"),
            ],
        }
    )

    result = fetch_and_sort_channels(api_caller=api_caller, members_only=False)

    assert len(result) == 2


def test_format_channel_table_empty_list() -> None:
    result = format_channel_table([])
    assert result == "No channels found.\n"


def test_format_channel_table_formats_channels() -> None:
    channels = [
        {"name": "general", "_latest_message_ts": 1700000000.0},
        {"name": "random", "_latest_message_ts": 1600000000.0},
    ]

    result = format_channel_table(channels)

    assert "general" in result
    assert "random" in result
    assert "2023-11-14" in result
    assert "CHANNEL" in result
    assert "LAST MESSAGE" in result
    assert "---" in result


def test_format_channel_table_shows_no_messages_when_timestamp_is_zero() -> None:
    channels = [{"name": "empty-channel", "_latest_message_ts": 0.0}]

    result = format_channel_table(channels)

    assert "empty-channel" in result
    assert "no messages" in result
