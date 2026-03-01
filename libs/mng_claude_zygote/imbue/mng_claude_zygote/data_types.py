from __future__ import annotations

from typing import Any
from typing import Final

from imbue.imbue_common.event_envelope import EventEnvelope
from imbue.imbue_common.event_envelope import EventSource
from imbue.imbue_common.primitives import NonEmptyStr


class ConversationId(NonEmptyStr):
    """Unique identifier for a conversation thread (matches llm's conversation_id format)."""


class ChatModel(NonEmptyStr):
    """Model name used for chat conversations (e.g. 'claude-sonnet-4-6')."""


class MessageRole(NonEmptyStr):
    """Role of a message sender (e.g. 'user', 'assistant')."""


# -- Event log sources --
# These constants define the source names and corresponding log paths.
# Each source writes to logs/<SOURCE>/events.jsonl.

SOURCE_CONVERSATIONS: Final[EventSource] = EventSource("conversations")
SOURCE_MESSAGES: Final[EventSource] = EventSource("messages")
SOURCE_SCHEDULED: Final[EventSource] = EventSource("scheduled")
SOURCE_MNG_AGENTS: Final[EventSource] = EventSource("mng_agents")
SOURCE_STOP: Final[EventSource] = EventSource("stop")
SOURCE_MONITOR: Final[EventSource] = EventSource("monitor")
SOURCE_CLAUDE_TRANSCRIPT: Final[EventSource] = EventSource("claude_transcript")


class ConversationEvent(EventEnvelope):
    """An event in logs/conversations/events.jsonl tracking conversation lifecycle.

    Emitted when a conversation is created or its model is changed.
    """

    conversation_id: ConversationId
    model: ChatModel


class MessageEvent(EventEnvelope):
    """An event in logs/messages/events.jsonl recording a conversation message.

    Each event represents a single user or assistant message. All messages
    across all conversations go into the same file, with conversation_id
    identifying which conversation the message belongs to.
    """

    conversation_id: ConversationId
    role: MessageRole
    content: str


class ChangelingEvent(EventEnvelope):
    """A generic event with a data payload, used for sources like scheduled,
    mng_agents, stop, and monitor.

    The data field carries event-type-specific payload.
    """

    data: dict[str, Any] = {}
