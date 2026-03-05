import json
from pathlib import Path

from imbue.slack_exporter.data_types import EventKind
from imbue.slack_exporter.primitives import SlackChannelId
from imbue.slack_exporter.primitives import SlackChannelName
from imbue.slack_exporter.primitives import SlackMessageTimestamp
from imbue.slack_exporter.store import append_records
from imbue.slack_exporter.store import load_existing_state
from imbue.slack_exporter.testing import make_stored_channel_info
from imbue.slack_exporter.testing import make_stored_message


def test_load_existing_state_returns_empty_when_file_does_not_exist(temp_output_path: Path) -> None:
    state_by_id, id_by_name = load_existing_state(temp_output_path)
    assert state_by_id == {}
    assert id_by_name == {}


def test_load_existing_state_loads_messages_and_tracks_latest_timestamp(temp_output_path: Path) -> None:
    msg1 = make_stored_message(ts="1700000000.000001")
    msg2 = make_stored_message(ts="1700000000.000009")
    temp_output_path.write_text(msg1.model_dump_json() + "\n" + msg2.model_dump_json() + "\n")

    state_by_id, id_by_name = load_existing_state(temp_output_path)

    assert SlackChannelId("C123") in state_by_id
    state = state_by_id[SlackChannelId("C123")]
    assert state.latest_message_timestamp == SlackMessageTimestamp("1700000000.000009")
    assert id_by_name[SlackChannelName("general")] == SlackChannelId("C123")


def test_load_existing_state_loads_channel_info_records(temp_output_path: Path) -> None:
    info = make_stored_channel_info()
    temp_output_path.write_text(info.model_dump_json() + "\n")

    state_by_id, id_by_name = load_existing_state(temp_output_path)

    assert state_by_id == {}
    assert id_by_name[SlackChannelName("general")] == SlackChannelId("C123")


def test_load_existing_state_skips_malformed_lines(temp_output_path: Path) -> None:
    msg = make_stored_message()
    temp_output_path.write_text("not valid json\n" + msg.model_dump_json() + "\n")

    state_by_id, _id_by_name = load_existing_state(temp_output_path)
    assert SlackChannelId("C123") in state_by_id


def test_load_existing_state_handles_multiple_channels(temp_output_path: Path) -> None:
    msg1 = make_stored_message(channel_id="C123", channel_name="general", ts="1700000000.000001")
    msg2 = make_stored_message(channel_id="C456", channel_name="random", ts="1700000000.000002")
    temp_output_path.write_text(msg1.model_dump_json() + "\n" + msg2.model_dump_json() + "\n")

    state_by_id, id_by_name = load_existing_state(temp_output_path)

    assert len(state_by_id) == 2
    assert id_by_name[SlackChannelName("general")] == SlackChannelId("C123")
    assert id_by_name[SlackChannelName("random")] == SlackChannelId("C456")


def test_append_records_creates_file_and_appends(temp_output_path: Path) -> None:
    msg = make_stored_message()
    append_records(temp_output_path, [msg])

    lines = temp_output_path.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == EventKind.MESSAGE
    assert parsed["channel_id"] == "C123"


def test_append_records_appends_to_existing_file(temp_output_path: Path) -> None:
    msg1 = make_stored_message(ts="1700000000.000001")
    append_records(temp_output_path, [msg1])

    msg2 = make_stored_message(ts="1700000000.000002")
    append_records(temp_output_path, [msg2])

    lines = temp_output_path.read_text().strip().splitlines()
    assert len(lines) == 2


def test_append_records_does_nothing_for_empty_list(temp_output_path: Path) -> None:
    append_records(temp_output_path, [])
    assert not temp_output_path.exists()


def test_append_records_appends_channel_info(temp_output_path: Path) -> None:
    info = make_stored_channel_info()
    append_records(temp_output_path, [info])

    lines = temp_output_path.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["kind"] == EventKind.CHANNEL_INFO
