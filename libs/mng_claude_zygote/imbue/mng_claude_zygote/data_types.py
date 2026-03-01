from __future__ import annotations

from typing import Any

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr


class ConversationId(NonEmptyStr):
    """Unique identifier for a conversation thread (matches llm's conversation_id format)."""


class ChatModel(NonEmptyStr):
    """Model name used for chat conversations (e.g. 'claude-sonnet-4-6')."""


class ConversationRecord(FrozenModel):
    """A record in conversations.jsonl tracking a conversation thread.

    Each line in conversations.jsonl is one of these records. Multiple entries
    for the same conversation ID are allowed (append-only); the last entry wins
    for fields like model.
    """

    id: ConversationId
    model: ChatModel
    timestamp: str


class EntrypointEvent(FrozenModel):
    """An event record in entrypoint_events.jsonl.

    Events trigger the primary agent's inner monologue to react. Event types
    include time-based triggers, sub-agent state changes, and shutdown checks.
    """

    type: str
    timestamp: str
    data: dict[str, Any] = {}


class ConversationMessage(FrozenModel):
    """A message synced from the llm database to a per-conversation JSONL file.

    Each line in conversations/<cid>.jsonl is one of these records, representing
    a single user or assistant message in timestamp order.
    """

    role: str
    content: str
    timestamp: str
    conversation_id: ConversationId
