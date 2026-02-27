from datetime import datetime
from typing import Any

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.zygote.primitives import MemoryKey
from imbue.zygote.primitives import MessageId
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.primitives import NotificationId
from imbue.zygote.primitives import NotificationSource
from imbue.zygote.primitives import ThreadId


class ThreadMessage(FrozenModel):
    """A single message in a chat thread."""

    id: MessageId = Field(description="Unique message identifier")
    role: MessageRole = Field(description="Who sent the message")
    content: str = Field(description="The message content")
    timestamp: datetime = Field(description="When the message was sent")


class Thread(FrozenModel):
    """A conversation thread between the agent and a user."""

    id: ThreadId = Field(description="Unique thread identifier")
    messages: tuple[ThreadMessage, ...] = Field(
        default=(),
        description="Ordered sequence of messages in this thread",
    )


class Notification(FrozenModel):
    """A notification delivered to the inner dialog agent.

    Notifications are the mechanism by which the inner dialog receives
    information about events -- user messages, sub-agent completions,
    system events, etc.
    """

    id: NotificationId = Field(description="Unique notification identifier")
    source: NotificationSource = Field(description="What generated this notification")
    content: str = Field(description="The notification content")
    thread_id: ThreadId | None = Field(
        default=None,
        description="The thread this notification relates to, if any",
    )
    timestamp: datetime = Field(description="When the notification was created")


class ToolResult(FrozenModel):
    """Result of executing a tool call from the inner dialog."""

    tool_use_id: str = Field(description="The tool_use block ID from the API response")
    content: str = Field(description="The result content")
    is_error: bool = Field(default=False, description="Whether the tool execution failed")


class InnerDialogState(FrozenModel):
    """The state of the inner dialog agent's conversation with the model.

    This tracks the full message history (in Claude API format) for the
    inner dialog, along with any compacted summary of older messages.
    """

    messages: tuple[dict[str, Any], ...] = Field(
        default=(),
        description="Message history in Claude API format",
    )
    compacted_summary: str | None = Field(
        default=None,
        description="Summary of compacted older messages, if any",
    )


class AgentMemory(FrozenModel):
    """Persistent key-value memory for the agent."""

    entries: dict[MemoryKey, str] = Field(
        default_factory=dict,
        description="Key-value store for agent memory",
    )


class ZygoteAgentConfig(FrozenModel):
    """Configuration for a ZygoteAgent instance.

    This defines the agent's identity, behavior (via system prompts),
    and model settings.
    """

    agent_name: str = Field(description="Human-readable name for this agent")
    agent_description: str = Field(description="Brief description of what this agent does")
    base_system_prompt: str = Field(description="Base system prompt shared between inner dialog and chat")
    inner_dialog_system_prompt: str = Field(description="Additional system prompt for the inner dialog agent loop")
    chat_system_prompt: str = Field(description="Additional system prompt for chat response generation")
    model: ModelName = Field(
        default=ModelName("claude-sonnet-4-5-20250514"),
        description="Claude model to use for API calls",
    )
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens per API response",
    )
    max_inner_dialog_messages: int = Field(
        default=100,
        description="Maximum number of messages before suggesting compaction",
    )
