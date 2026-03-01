from __future__ import annotations

from typing import Any

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr


class ConversationId(NonEmptyStr):
    """Unique identifier for a conversation thread (matches llm's conversation_id format)."""


class ChatModel(NonEmptyStr):
    """Model name used for chat conversations (e.g. 'claude-sonnet-4-6')."""


class IsoTimestamp(NonEmptyStr):
    """An ISO 8601 formatted timestamp string with nanosecond precision.

    Example: '2026-02-28T00:00:00.123456789Z'
    """


class EventType(NonEmptyStr):
    """Type of an event (e.g. 'conversation_created', 'message', 'scheduled')."""


class EventSource(NonEmptyStr):
    """Source identifier for an event, matching the log folder name.

    Must match the folder under logs/ where the event is stored.
    Examples: 'conversations', 'messages', 'entrypoint'
    """


class EventId(NonEmptyStr):
    """Unique identifier for an event (typically timestamp + random hex)."""


class MessageRole(NonEmptyStr):
    """Role of a message sender (e.g. 'user', 'assistant')."""


# -- Event log sources --
# These constants define the source names and corresponding log paths.
# Each source writes to logs/<SOURCE>/events.jsonl.

SOURCE_CONVERSATIONS = EventSource("conversations")
SOURCE_MESSAGES = EventSource("messages")
SOURCE_ENTRYPOINT = EventSource("entrypoint")
SOURCE_TRANSCRIPT = EventSource("transcript")


class ConversationEvent(FrozenModel):
    """An event in logs/conversations/events.jsonl tracking conversation lifecycle.

    Emitted when a conversation is created or its model is changed.
    Every event includes the standard envelope fields (timestamp, type,
    event_id, source) plus conversation-specific fields.
    """

    timestamp: IsoTimestamp
    type: EventType
    event_id: EventId
    source: EventSource
    conversation_id: ConversationId
    model: ChatModel


class MessageEvent(FrozenModel):
    """An event in logs/messages/events.jsonl recording a conversation message.

    Each event represents a single user or assistant message. All messages
    across all conversations go into the same file, with conversation_id
    identifying which conversation the message belongs to.
    """

    timestamp: IsoTimestamp
    type: EventType
    event_id: EventId
    source: EventSource
    conversation_id: ConversationId
    role: MessageRole
    content: str


class EntrypointEvent(FrozenModel):
    """An event in logs/entrypoint/events.jsonl that triggers the inner monologue.

    Event types include time-based triggers, sub-agent state changes,
    and shutdown checks. The data field carries event-type-specific payload.
    """

    timestamp: IsoTimestamp
    type: EventType
    event_id: EventId
    source: EventSource
    data: dict[str, Any] = {}
