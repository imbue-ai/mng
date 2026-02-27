"""Chat response generation for user threads.

To generate a reply for a given thread, we call a language model with:
1. The chat system prompt (base + chat-specific)
2. The full conversation history for that thread
3. A context message with the inner dialog agent's current state
"""

from typing import Any
from typing import assert_never

import anthropic

from imbue.imbue_common.pure import pure
from imbue.zygote.data_types import Thread
from imbue.zygote.errors import ChatResponseError
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.prompts import build_chat_full_prompt


@pure
def _role_to_api_string(role: MessageRole) -> str:
    """Convert a MessageRole enum to the Claude API role string."""
    match role:
        case MessageRole.USER:
            return "user"
        case MessageRole.ASSISTANT:
            return "assistant"
        case _ as unreachable:
            assert_never(unreachable)


@pure
def _thread_to_api_messages(thread: Thread) -> list[dict[str, Any]]:
    """Convert a Thread's messages into Claude API message format."""
    return [
        {
            "role": _role_to_api_string(msg.role),
            "content": msg.content,
        }
        for msg in thread.messages
    ]


async def generate_chat_response(
    thread: Thread,
    inner_dialog_summary: str,
    base_system_prompt: str,
    chat_system_prompt: str,
    client: anthropic.AsyncAnthropic,
    model: ModelName,
    max_tokens: int = 4096,
) -> str:
    """Generate a chat response for a thread.

    Combines the base and chat system prompts with the inner dialog's
    current state summary, then calls the model with the full thread
    conversation history to produce a response.
    """
    full_system = build_chat_full_prompt(
        base_prompt=base_system_prompt,
        chat_prompt=chat_system_prompt,
        inner_dialog_summary=inner_dialog_summary,
    )

    api_messages = _thread_to_api_messages(thread)

    if not api_messages:
        raise ChatResponseError("Cannot generate a response for an empty thread")

    # Ensure the last message is from the user (required by the API)
    if api_messages[-1]["role"] != "user":
        raise ChatResponseError("Cannot generate a response: last message must be from the user")

    try:
        response = await client.messages.create(
            model=str(model),
            max_tokens=max_tokens,
            system=full_system,
            messages=api_messages,
        )
    except anthropic.APIError as e:
        raise ChatResponseError(f"API error generating chat response: {e}") from e

    text_parts: list[str] = []
    for block in response.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)

    if not text_parts:
        raise ChatResponseError("Model returned no text content in response")

    return "".join(text_parts)
