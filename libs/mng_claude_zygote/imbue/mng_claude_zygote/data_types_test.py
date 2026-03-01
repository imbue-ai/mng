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


class TestConversationId:
    def test_valid_id(self) -> None:
        cid = ConversationId("abc123")
        assert str(cid) == "abc123"

    def test_strips_whitespace(self) -> None:
        cid = ConversationId("  abc123  ")
        assert str(cid) == "abc123"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ConversationId("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ConversationId("   ")


class TestChatModel:
    def test_valid_model(self) -> None:
        model = ChatModel("claude-sonnet-4-6")
        assert str(model) == "claude-sonnet-4-6"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            ChatModel("")


class TestIsoTimestamp:
    def test_valid_timestamp(self) -> None:
        ts = IsoTimestamp("2026-02-28T00:00:00Z")
        assert str(ts) == "2026-02-28T00:00:00Z"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            IsoTimestamp("")


class TestEventType:
    def test_valid_type(self) -> None:
        et = EventType("scheduled")
        assert str(et) == "scheduled"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            EventType("")


class TestMessageRole:
    def test_valid_role(self) -> None:
        role = MessageRole("user")
        assert str(role) == "user"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            MessageRole("")


class TestConversationRecord:
    def test_construction(self) -> None:
        record = ConversationRecord(
            id=ConversationId("conv-1"),
            model=ChatModel("claude-sonnet-4-6"),
            timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        )
        assert record.id == "conv-1"
        assert record.model == "claude-sonnet-4-6"
        assert record.timestamp == "2026-02-28T00:00:00Z"

    def test_serializes_to_json(self) -> None:
        record = ConversationRecord(
            id=ConversationId("conv-1"),
            model=ChatModel("claude-sonnet-4-6"),
            timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        )
        data = json.loads(record.model_dump_json())
        assert data["id"] == "conv-1"
        assert data["model"] == "claude-sonnet-4-6"

    def test_is_frozen(self) -> None:
        record = ConversationRecord(
            id=ConversationId("conv-1"),
            model=ChatModel("claude-sonnet-4-6"),
            timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
        )
        with pytest.raises(Exception):
            record.id = ConversationId("conv-2")  # type: ignore[misc]


class TestEntrypointEvent:
    def test_construction_with_defaults(self) -> None:
        event = EntrypointEvent(type=EventType("scheduled"), timestamp=IsoTimestamp("2026-02-28T00:00:00Z"))
        assert event.type == "scheduled"
        assert event.data == {}

    def test_construction_with_data(self) -> None:
        event = EntrypointEvent(
            type=EventType("sub_agent_waiting"),
            timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
            data={"agent_name": "helper-1"},
        )
        assert event.data["agent_name"] == "helper-1"

    def test_serializes_to_json(self) -> None:
        event = EntrypointEvent(
            type=EventType("scheduled"),
            timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
            data={"key": "value"},
        )
        data = json.loads(event.model_dump_json())
        assert data["type"] == "scheduled"
        assert data["data"]["key"] == "value"


class TestConversationMessage:
    def test_construction(self) -> None:
        msg = ConversationMessage(
            role=MessageRole("user"),
            content="Hello",
            timestamp=IsoTimestamp("2026-02-28T00:00:00Z"),
            conversation_id=ConversationId("conv-1"),
        )
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.conversation_id == "conv-1"

    def test_serializes_to_single_json_line(self) -> None:
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
