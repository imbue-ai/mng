"""Unit tests for changeling data types."""

import json

import pytest

from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.data_types import ConversationId
from imbue.mng_claude_zygote.data_types import ConversationMessage
from imbue.mng_claude_zygote.data_types import ConversationRecord
from imbue.mng_claude_zygote.data_types import EntrypointEvent
from imbue.mng_claude_zygote.data_types import EventType
from imbue.mng_claude_zygote.data_types import IsoTimestamp
from imbue.mng_claude_zygote.data_types import MessageRole

# -- ConversationId --


def test_conversation_id_accepts_valid_string() -> None:
    cid = ConversationId("abc123")
    assert str(cid) == "abc123"


def test_conversation_id_strips_whitespace() -> None:
    cid = ConversationId("  abc123  ")
    assert str(cid) == "abc123"


def test_conversation_id_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ConversationId("")


def test_conversation_id_rejects_whitespace_only() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ConversationId("   ")


# -- ChatModel --


def test_chat_model_accepts_valid_string() -> None:
    model = ChatModel("claude-sonnet-4-6")
    assert str(model) == "claude-sonnet-4-6"


def test_chat_model_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ChatModel("")


# -- IsoTimestamp --


def test_iso_timestamp_accepts_valid_string() -> None:
    ts = IsoTimestamp("2026-02-28T00:00:00Z")
    assert str(ts) == "2026-02-28T00:00:00Z"


def test_iso_timestamp_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        IsoTimestamp("")


# -- EventType --


def test_event_type_accepts_valid_string() -> None:
    et = EventType("scheduled")
    assert str(et) == "scheduled"


def test_event_type_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        EventType("")


# -- MessageRole --


def test_message_role_accepts_valid_string() -> None:
    role = MessageRole("user")
    assert str(role) == "user"


def test_message_role_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        MessageRole("")


# -- ConversationRecord --


def test_conversation_record_construction() -> None:
    record = ConversationRecord(
        id=ConversationId("conv-1"),
        model=ChatModel("claude-sonnet-4-6"),
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
    )
    assert record.id == "conv-1"
    assert record.model == "claude-sonnet-4-6"
    assert record.timestamp == "2026-02-28T00:00:00Z"


def test_conversation_record_serializes_to_json() -> None:
    record = ConversationRecord(
        id=ConversationId("conv-1"),
        model=ChatModel("claude-sonnet-4-6"),
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
    )
    data = json.loads(record.model_dump_json())
    assert data["id"] == "conv-1"
    assert data["model"] == "claude-sonnet-4-6"


def test_conversation_record_is_frozen() -> None:
    record = ConversationRecord(
        id=ConversationId("conv-1"),
        model=ChatModel("claude-sonnet-4-6"),
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
    )
    with pytest.raises(Exception):
        record.id = ConversationId("conv-2")  # type: ignore[misc]


# -- EntrypointEvent --


def test_entrypoint_event_construction_with_defaults() -> None:
    event = EntrypointEvent(type=EventType("scheduled"), timestamp=IsoTimestamp("2026-02-28T00:00:00Z"))
    assert event.type == "scheduled"
    assert event.data == {}


def test_entrypoint_event_construction_with_data() -> None:
    event = EntrypointEvent(
        type=EventType("sub_agent_waiting"),
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        data={"agent_name": "helper-1"},
    )
    assert event.data["agent_name"] == "helper-1"


def test_entrypoint_event_serializes_to_json() -> None:
    event = EntrypointEvent(
        type=EventType("scheduled"),
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        data={"key": "value"},
    )
    data = json.loads(event.model_dump_json())
    assert data["type"] == "scheduled"
    assert data["data"]["key"] == "value"


# -- ConversationMessage --


def test_conversation_message_construction() -> None:
    msg = ConversationMessage(
        role=MessageRole("user"),
        content="Hello",
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        conversation_id=ConversationId("conv-1"),
    )
    assert msg.role == "user"
    assert msg.content == "Hello"
    assert msg.conversation_id == "conv-1"


def test_conversation_message_serializes_to_single_json_line() -> None:
    msg = ConversationMessage(
        role=MessageRole("assistant"),
        content="Hi there!",
        timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        conversation_id=ConversationId("conv-1"),
    )
    json_str = msg.model_dump_json()
    assert "\n" not in json_str
    data = json.loads(json_str)
    assert data["role"] == "assistant"
