"""Unit tests for changeling data types."""

import json

import pytest

from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.data_types import ConversationEvent
from imbue.mng_claude_zygote.data_types import ConversationId
from imbue.mng_claude_zygote.data_types import EntrypointEvent
from imbue.mng_claude_zygote.data_types import EventId
from imbue.mng_claude_zygote.data_types import EventSource
from imbue.mng_claude_zygote.data_types import EventType
from imbue.mng_claude_zygote.data_types import IsoTimestamp
from imbue.mng_claude_zygote.data_types import MessageEvent
from imbue.mng_claude_zygote.data_types import MessageRole
from imbue.mng_claude_zygote.data_types import SOURCE_CONVERSATIONS
from imbue.mng_claude_zygote.data_types import SOURCE_ENTRYPOINT
from imbue.mng_claude_zygote.data_types import SOURCE_MESSAGES

_TS = IsoTimestamp("2026-02-28T00:00:00.000000000Z")
_EID = EventId("evt-1234")


# -- Primitive types --


def test_conversation_id_accepts_valid_string() -> None:
    assert str(ConversationId("abc123")) == "abc123"


def test_conversation_id_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ConversationId("")


def test_chat_model_accepts_valid_string() -> None:
    assert str(ChatModel("claude-sonnet-4-6")) == "claude-sonnet-4-6"


def test_chat_model_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ChatModel("")


def test_iso_timestamp_accepts_nanosecond_precision() -> None:
    assert str(IsoTimestamp("2026-02-28T00:00:00.000000000Z")) == "2026-02-28T00:00:00.000000000Z"


def test_iso_timestamp_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        IsoTimestamp("")


def test_event_type_accepts_valid_string() -> None:
    assert str(EventType("conversation_created")) == "conversation_created"


def test_event_source_accepts_valid_string() -> None:
    assert str(EventSource("conversations")) == "conversations"


def test_event_id_accepts_valid_string() -> None:
    assert str(EventId("evt-abc123")) == "evt-abc123"


def test_message_role_accepts_valid_string() -> None:
    assert str(MessageRole("user")) == "user"


# -- Source constants --


def test_source_constants_are_valid() -> None:
    assert SOURCE_CONVERSATIONS == "conversations"
    assert SOURCE_MESSAGES == "messages"
    assert SOURCE_ENTRYPOINT == "entrypoint"


# -- ConversationEvent --


def test_conversation_event_has_all_envelope_fields() -> None:
    event = ConversationEvent(
        timestamp=_TS,
        type=EventType("conversation_created"),
        event_id=_EID,
        source=SOURCE_CONVERSATIONS,
        conversation_id=ConversationId("conv-1"),
        model=ChatModel("claude-opus-4-6"),
    )
    data = json.loads(event.model_dump_json())
    assert "timestamp" in data
    assert "type" in data
    assert "event_id" in data
    assert "source" in data


def test_conversation_event_is_self_describing() -> None:
    event = ConversationEvent(
        timestamp=_TS,
        type=EventType("conversation_created"),
        event_id=_EID,
        source=SOURCE_CONVERSATIONS,
        conversation_id=ConversationId("conv-1"),
        model=ChatModel("claude-opus-4-6"),
    )
    data = json.loads(event.model_dump_json())
    assert data["source"] == "conversations"
    assert data["conversation_id"] == "conv-1"
    assert data["model"] == "claude-opus-4-6"


def test_conversation_event_is_frozen() -> None:
    event = ConversationEvent(
        timestamp=_TS,
        type=EventType("conversation_created"),
        event_id=_EID,
        source=SOURCE_CONVERSATIONS,
        conversation_id=ConversationId("conv-1"),
        model=ChatModel("claude-opus-4-6"),
    )
    with pytest.raises(Exception):
        event.conversation_id = ConversationId("conv-2")  # type: ignore[misc]


# -- MessageEvent --


def test_message_event_includes_conversation_id() -> None:
    """Every message is self-describing: you never need to know the filename."""
    event = MessageEvent(
        timestamp=_TS,
        type=EventType("message"),
        event_id=_EID,
        source=SOURCE_MESSAGES,
        conversation_id=ConversationId("conv-1"),
        role=MessageRole("user"),
        content="Hello",
    )
    data = json.loads(event.model_dump_json())
    assert data["conversation_id"] == "conv-1"
    assert data["role"] == "user"
    assert data["source"] == "messages"


def test_message_event_serializes_to_single_json_line() -> None:
    event = MessageEvent(
        timestamp=_TS,
        type=EventType("message"),
        event_id=_EID,
        source=SOURCE_MESSAGES,
        conversation_id=ConversationId("conv-1"),
        role=MessageRole("assistant"),
        content="Hi there!",
    )
    json_str = event.model_dump_json()
    assert "\n" not in json_str


# -- EntrypointEvent --


def test_entrypoint_event_construction_with_defaults() -> None:
    event = EntrypointEvent(
        timestamp=_TS,
        type=EventType("scheduled"),
        event_id=_EID,
        source=SOURCE_ENTRYPOINT,
    )
    assert event.type == "scheduled"
    assert event.data == {}
    assert event.source == "entrypoint"


def test_entrypoint_event_construction_with_data() -> None:
    event = EntrypointEvent(
        timestamp=_TS,
        type=EventType("sub_agent_waiting"),
        event_id=_EID,
        source=SOURCE_ENTRYPOINT,
        data={"agent_name": "helper-1"},
    )
    assert event.data["agent_name"] == "helper-1"


def test_entrypoint_event_has_all_envelope_fields() -> None:
    event = EntrypointEvent(
        timestamp=_TS,
        type=EventType("scheduled"),
        event_id=_EID,
        source=SOURCE_ENTRYPOINT,
        data={"key": "value"},
    )
    data = json.loads(event.model_dump_json())
    assert data["timestamp"] == str(_TS)
    assert data["type"] == "scheduled"
    assert data["event_id"] == str(_EID)
    assert data["source"] == "entrypoint"
