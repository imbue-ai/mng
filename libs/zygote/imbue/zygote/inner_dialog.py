"""The inner dialog agent loop.

The inner dialog is the core of the zygote agent. It receives notifications
(user messages, system events, sub-agent completions) and processes them by
calling the Claude API with tools. The agent continues calling tools until
it has nothing more to do, at which point it yields control.

All actual logic comes from the system prompt -- the inner dialog loop is
a generic event-driven agent loop that executes whatever the system prompt
instructs.
"""

import json
from typing import Any
from typing import Final

import anthropic

from imbue.imbue_common.pure import pure
from imbue.zygote.data_types import ContentBlock
from imbue.zygote.data_types import InnerDialogMessage
from imbue.zygote.data_types import InnerDialogState
from imbue.zygote.data_types import Notification
from imbue.zygote.data_types import ToolResult
from imbue.zygote.errors import CompactionError
from imbue.zygote.errors import InnerDialogError
from imbue.zygote.interfaces import ToolExecutorInterface
from imbue.zygote.primitives import MessageRole
from imbue.zygote.primitives import ModelName
from imbue.zygote.prompts import build_compaction_prompt
from imbue.zygote.tools import ALL_TOOLS
from imbue.zygote.tools import execute_tool

DEFAULT_MAX_TOOL_ITERATIONS: Final[int] = 50


@pure
def _build_notification_user_message(notification: Notification) -> InnerDialogMessage:
    """Convert a notification into a user message for the inner dialog."""
    thread_context = ""
    if notification.thread_id is not None:
        thread_context = f" [thread: {notification.thread_id}]"
    return InnerDialogMessage(
        role=MessageRole.USER,
        content=f"[{notification.source.value} notification{thread_context}]\n{notification.content}",
    )


@pure
def _build_system_with_summary(system_prompt: str, compacted_summary: str | None) -> str:
    """Build the system prompt, prepending any compacted history summary."""
    if compacted_summary is None:
        return system_prompt
    return (
        f"{system_prompt}\n\n"
        f"# Previous Context (Compacted)\n\n"
        f"The following is a summary of earlier conversation that has been "
        f"compacted to save space:\n\n{compacted_summary}"
    )


@pure
def _extract_tool_use_blocks(response: anthropic.types.Message) -> list[anthropic.types.ToolUseBlock]:
    """Extract all tool_use blocks from a response."""
    return [block for block in response.content if isinstance(block, anthropic.types.ToolUseBlock)]


@pure
def _build_tool_result_message(results: list[ToolResult]) -> InnerDialogMessage:
    """Build a tool_result user message from tool execution results."""
    blocks = tuple(
        ContentBlock(
            type="tool_result",
            data={
                "tool_use_id": result.tool_use_id,
                "content": result.content,
                "is_error": result.is_error,
            },
        )
        for result in results
    )
    return InnerDialogMessage(role=MessageRole.USER, content=blocks)


@pure
def _response_to_message(response: anthropic.types.Message) -> InnerDialogMessage:
    """Convert an API response to an InnerDialogMessage."""
    blocks = tuple(
        ContentBlock.from_api_dict(
            block.model_dump() if hasattr(block, "model_dump") else {"type": "text", "text": str(block)}
        )
        for block in response.content
    )
    return InnerDialogMessage(role=MessageRole.ASSISTANT, content=blocks)


async def process_notification(
    state: InnerDialogState,
    notification: Notification,
    system_prompt: str,
    tool_executor: ToolExecutorInterface,
    client: anthropic.AsyncAnthropic,
    model: ModelName,
    max_tokens: int = 4096,
    max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
) -> InnerDialogState:
    """Process a notification through the inner dialog loop.

    This is the core agent loop:
    1. Add the notification as a user message
    2. Call Claude with the system prompt and tools
    3. If Claude calls tools, execute them and continue
    4. Repeat until Claude responds without tool calls
    5. Return the updated state

    The loop is event-driven: it processes one notification at a time and
    yields control when done. The agent is re-activated by the next notification.
    """
    notification_message = _build_notification_user_message(notification)
    messages = list(state.messages) + [notification_message]
    full_system = _build_system_with_summary(system_prompt, state.compacted_summary)

    try:
        messages = await _run_tool_loop(
            messages=messages,
            system_prompt=full_system,
            tool_executor=tool_executor,
            client=client,
            model=model,
            max_tokens=max_tokens,
            max_iterations=max_tool_iterations,
        )
    except anthropic.APIError as e:
        raise InnerDialogError(f"API error during inner dialog: {e}") from e

    return InnerDialogState(
        messages=tuple(messages),
        compacted_summary=state.compacted_summary,
    )


def _messages_to_api_format(messages: list[InnerDialogMessage]) -> list[dict[str, Any]]:
    """Convert typed messages to Claude API format for the messages parameter."""
    return [msg.to_api_dict() for msg in messages]


async def _run_tool_loop(
    messages: list[InnerDialogMessage],
    system_prompt: str,
    tool_executor: ToolExecutorInterface,
    client: anthropic.AsyncAnthropic,
    model: ModelName,
    max_tokens: int,
    max_iterations: int,
) -> list[InnerDialogMessage]:
    """Run the tool execution loop until the model stops calling tools.

    Raises InnerDialogError if max_iterations is exceeded.
    """
    for _ in range(max_iterations):
        response = await client.messages.create(
            model=str(model),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=_messages_to_api_format(messages),
            tools=list(ALL_TOOLS),
        )

        assistant_message = _response_to_message(response)
        messages.append(assistant_message)

        tool_use_blocks = _extract_tool_use_blocks(response)

        if not tool_use_blocks:
            return messages

        results = []
        for tool_use in tool_use_blocks:
            tool_input = tool_use.input if isinstance(tool_use.input, dict) else {}
            result = await execute_tool(
                tool_name=tool_use.name,
                tool_input=tool_input,
                tool_use_id=tool_use.id,
                executor=tool_executor,
            )
            results.append(result)

        tool_result_msg = _build_tool_result_message(results)
        messages.append(tool_result_msg)

    raise InnerDialogError(f"Tool loop exceeded maximum iterations ({max_iterations})")


async def compact_inner_dialog(
    state: InnerDialogState,
    client: anthropic.AsyncAnthropic,
    model: ModelName,
    max_tokens: int = 4096,
    messages_to_preserve: int = 10,
) -> InnerDialogState:
    """Compact the inner dialog history by summarizing older messages.

    Keeps the most recent messages_to_preserve messages intact and summarizes
    everything older into a compacted summary. The summary is prepended to the
    system prompt on future calls.
    """
    messages = list(state.messages)

    if len(messages) <= messages_to_preserve:
        return state

    older_messages = messages[:-messages_to_preserve]
    preserved_messages = messages[-messages_to_preserve:]

    messages_text = json.dumps([msg.to_api_dict() for msg in older_messages], indent=2)

    compaction_prompt = build_compaction_prompt(messages_text)

    existing_summary = state.compacted_summary or ""
    if existing_summary:
        compaction_prompt = (
            f"Previous summary:\n{existing_summary}\n\nAdditional conversation to incorporate:\n{compaction_prompt}"
        )

    try:
        response = await client.messages.create(
            model=str(model),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": compaction_prompt}],
        )
    except anthropic.APIError as e:
        raise CompactionError(f"API error during compaction: {e}") from e

    summary_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            summary_text += block.text

    if not summary_text:
        raise CompactionError("Compaction produced no summary text")

    return InnerDialogState(
        messages=tuple(preserved_messages),
        compacted_summary=summary_text,
    )


@pure
def get_inner_dialog_summary(state: InnerDialogState) -> str:
    """Generate a brief summary of the inner dialog's current state.

    This is used as context for chat responses, giving the chat model
    awareness of the agent's broader activity.
    """
    parts: list[str] = []

    if state.compacted_summary:
        parts.append(f"Historical context: {state.compacted_summary}")

    recent_messages = state.messages[-5:] if state.messages else ()
    if recent_messages:
        recent_texts: list[str] = []
        for msg in recent_messages:
            role = msg.role.value.lower()
            if isinstance(msg.content, str):
                recent_texts.append(f"  {role}: {msg.content[:200]}")
            else:
                text_parts = [block.data.get("text", "") for block in msg.content if block.type == "text"]
                if text_parts:
                    recent_texts.append(f"  {role}: {''.join(text_parts)[:200]}")
        if recent_texts:
            parts.append("Recent inner dialog:\n" + "\n".join(recent_texts))

    if not parts:
        return "The agent has no prior activity."

    return "\n\n".join(parts)
