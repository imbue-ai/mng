from imbue.imbue_common.pure import pure


@pure
def build_inner_dialog_full_prompt(base_prompt: str, inner_dialog_prompt: str) -> str:
    """Combine the base and inner dialog system prompts.

    The inner dialog prompt is appended to the base prompt, separated by
    a section header. This is the full system prompt used for the inner
    dialog agent loop.
    """
    return f"{base_prompt}\n\n# Inner Dialog Instructions\n\n{inner_dialog_prompt}"


@pure
def build_chat_full_prompt(
    base_prompt: str,
    chat_prompt: str,
    inner_dialog_summary: str,
) -> str:
    """Combine the base prompt, chat prompt, and inner dialog state for chat responses.

    The chat system prompt includes:
    1. The base prompt (shared identity and capabilities)
    2. The chat-specific instructions
    3. A summary of the inner dialog agent's current state, so the chat
       response can be informed by the agent's broader context and activity.
    """
    parts = [
        base_prompt,
        f"\n\n# Chat Response Instructions\n\n{chat_prompt}",
    ]
    if inner_dialog_summary:
        parts.append(
            f"\n\n# Current Agent State\n\n"
            f"The following is a summary of your current internal state and activity "
            f"across all threads and tasks:\n\n{inner_dialog_summary}"
        )
    return "".join(parts)


@pure
def build_compaction_prompt(messages_text: str) -> str:
    """Build the prompt for compacting conversation history.

    This prompt asks the model to summarize the conversation so far into
    a concise summary that preserves key context, decisions, and state.
    """
    return (
        "Summarize the following conversation history into a concise summary. "
        "Preserve key context, decisions made, ongoing tasks, and important state. "
        "The summary should be detailed enough that the conversation can continue "
        "meaningfully with only the summary as context for the older messages.\n\n"
        f"Conversation to summarize:\n{messages_text}"
    )
