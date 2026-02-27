from __future__ import annotations

import shlex
from typing import Any

from imbue.mng import hookimpl
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.primitives import CommandString
from imbue.mng_claude_zygote.plugin import ClaudeZygoteAgent
from imbue.mng_claude_zygote.plugin import inject_agent_ttyd

ELENA_SYSTEM_PROMPT = (
    "You are Elena, a friendly and conversational AI assistant. "
    "Your purpose is to have engaging conversations, answer questions, and help users think through problems. "
    "You should be warm, thoughtful, and direct in your responses. "
    "IMPORTANT: You must NEVER write code, create files, or make any changes to the filesystem. "
    "You are purely conversational. If a user asks you to write code, politely explain that you are a conversational "
    "assistant and suggest they use a different tool for coding tasks. "
    "Keep your responses concise and focused on the conversation."
)


class ElenaCodeAgent(ClaudeZygoteAgent):
    """A conversational AI changeling agent powered by Claude Code.

    Elena is designed to be purely conversational -- she interacts with users
    via a web-accessible Claude Code session but is instructed to never write
    code or modify files. Her system prompt encourages friendly, thoughtful
    conversation.
    """

    def assemble_command(
        self,
        host: OnlineHostInterface,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString:
        """Assemble command with Elena's system prompt appended."""
        system_prompt_args = ("--append-system-prompt", shlex.quote(ELENA_SYSTEM_PROMPT))
        extended_args = system_prompt_args + agent_args
        return super().assemble_command(host, extended_args, command_override)


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface], type[AgentTypeConfig]]:
    """Register the elena-code agent type."""
    return ("elena-code", ElenaCodeAgent, ClaudeAgentConfig)


@hookimpl
def override_command_options(
    command_name: str,
    command_class: type,
    params: dict[str, Any],
) -> None:
    """Add an agent ttyd web terminal when creating elena-code agents."""
    if command_name != "create":
        return

    agent_type = params.get("agent_type") or params.get("positional_agent_type")
    if agent_type != "elena-code":
        return

    inject_agent_ttyd(params)
