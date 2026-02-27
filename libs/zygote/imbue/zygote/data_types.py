from datetime import datetime
from typing import Any

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr
from imbue.imbue_common.primitives import PositiveInt
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


class ContentBlock(FrozenModel):
    """A content block in a Claude API message (text, tool_use, or tool_result).

    Uses a flexible data field to store block-specific attributes alongside
    the required type field.
    """

    type: str = Field(description="Block type (text, tool_use, tool_result)")
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Block-specific data (text, tool_use_id, input, etc.)",
    )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize to a flat dict for the Claude API."""
        result = dict(self.data)
        result["type"] = self.type
        return result

    @classmethod
    def from_api_dict(cls, raw: dict[str, Any]) -> "ContentBlock":
        """Construct from a Claude API content block dict."""
        block_type = raw["type"]
        data = {k: v for k, v in raw.items() if k != "type"}
        return cls(type=block_type, data=data)


class InnerDialogMessage(FrozenModel):
    """A typed message in the inner dialog's conversation history.

    Wraps the Claude API message format with proper types. Content can be
    either a plain string (for simple messages) or a tuple of content blocks
    (for tool use/result messages).
    """

    role: MessageRole = Field(description="Message role (USER or ASSISTANT)")
    content: str | tuple[ContentBlock, ...] = Field(description="Message content")

    def to_api_dict(self) -> dict[str, Any]:
        """Convert to Claude API message format."""
        if isinstance(self.content, str):
            return {"role": self.role.value.lower(), "content": self.content}
        return {
            "role": self.role.value.lower(),
            "content": [block.model_dump() for block in self.content],
        }

    @classmethod
    def from_api_dict(cls, data: dict[str, Any]) -> "InnerDialogMessage":
        """Construct from a Claude API message dict."""
        role = MessageRole(data["role"].upper())
        raw_content = data["content"]
        if isinstance(raw_content, str):
            content: str | tuple[ContentBlock, ...] = raw_content
        else:
            content = tuple(ContentBlock.from_api_dict(block) for block in raw_content)
        return cls(role=role, content=content)


class InnerDialogState(FrozenModel):
    """The state of the inner dialog agent's conversation with the model.

    This tracks the full message history for the inner dialog, along with
    any compacted summary of older messages.
    """

    messages: tuple[InnerDialogMessage, ...] = Field(
        default=(),
        description="Message history",
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

    agent_name: NonEmptyStr = Field(description="Human-readable name for this agent")
    agent_description: NonEmptyStr = Field(description="Brief description of what this agent does")
    base_system_prompt: NonEmptyStr = Field(description="Base system prompt shared between inner dialog and chat")
    inner_dialog_system_prompt: NonEmptyStr = Field(
        description="Additional system prompt for the inner dialog agent loop"
    )
    chat_system_prompt: NonEmptyStr = Field(description="Additional system prompt for chat response generation")
    model: ModelName = Field(
        default=ModelName("claude-sonnet-4-5-20250514"),
        description="Claude model to use for API calls",
    )
    max_tokens: PositiveInt = Field(
        default=PositiveInt(4096),
        description="Maximum tokens per API response",
    )
    max_inner_dialog_messages: PositiveInt = Field(
        default=PositiveInt(100),
        description="Maximum number of messages before suggesting compaction",
    )
