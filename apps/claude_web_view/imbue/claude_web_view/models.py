from enum import Enum
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class MessageRole(str, Enum):
    """Role of a message in the conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# Content block types
class TextBlock(BaseModel):
    """A text content block."""

    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    """A tool use content block."""

    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """A tool result content block."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str  # Normalized to string for display
    is_error: bool = False


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


class ParsedMessage(BaseModel):
    """A parsed message from the transcript."""

    id: str
    role: MessageRole
    content: list[ContentBlock] = Field(default_factory=list)
    timestamp: str | None = None


class SessionMetadata(BaseModel):
    """Metadata about a Claude Code session."""

    session_id: str
    model: str
    tools: list[str] = Field(default_factory=list)


# SSE event types for frontend
class SSEInitEvent(BaseModel):
    """Initial SSE event with session state."""

    type: Literal["init"] = "init"
    metadata: SessionMetadata | None
    messages: list[ParsedMessage]


class SSEMessageEvent(BaseModel):
    """New message SSE event."""

    type: Literal["message"] = "message"
    message: ParsedMessage


class SSECompleteEvent(BaseModel):
    """Session complete SSE event."""

    type: Literal["complete"] = "complete"
    duration_ms: float | None = None
    total_cost_usd: float | None = None


class SSEErrorEvent(BaseModel):
    """Error SSE event."""

    type: Literal["error"] = "error"
    error: str
