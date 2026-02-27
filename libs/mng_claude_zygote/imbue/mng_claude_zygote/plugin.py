from __future__ import annotations

from typing import Any

from imbue.mng import hookimpl
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng_ttyd.plugin import build_ttyd_server_command

AGENT_TTYD_WINDOW_NAME = "agent"
AGENT_TTYD_SERVER_NAME = "agent"

# Bash wrapper that starts ttyd attached to the agent's own tmux session.
# This allows users to interact with the Claude agent via a web browser.
#
# How it works:
# 1. Gets the current tmux session name (the agent's session)
# 2. Starts ttyd on a random port (-p 0) running `tmux attach` to that session
#    - Unsets TMUX env var so tmux allows the nested attach from ttyd's child process
# 3. Watches ttyd's stderr for the assigned port number (via shared helper)
# 4. Writes a servers.jsonl record so the changelings forwarding server can discover it
_AGENT_TTYD_INVOCATION = (
    "_SESSION=$(tmux display-message -p '#{session_name}') && "
    'ttyd -p 0 bash -c \'unset TMUX && exec tmux attach -t "$1":0\' -- "$_SESSION"'
)

AGENT_TTYD_COMMAND = build_ttyd_server_command(_AGENT_TTYD_INVOCATION, AGENT_TTYD_SERVER_NAME)


class ClaudeZygoteAgent(ClaudeAgent):
    """Base agent for changeling agents built on Claude Code.

    Inherits all Claude Code functionality (session management, provisioning,
    TUI interaction, etc.) and is intended as a base class for specialized
    changeling agents that need a web-accessible Claude interface.
    """


def inject_agent_ttyd(params: dict[str, Any]) -> None:
    """Inject an agent ttyd window into the create command parameters.

    This adds a ttyd web terminal that attaches to the agent's tmux session,
    allowing users to interact with the Claude agent via a web browser.

    Intended to be called from override_command_options hooks by plugins
    that register ClaudeZygoteAgent subtypes.
    """
    existing = params.get("add_command", ())
    params["add_command"] = (*existing, f'{AGENT_TTYD_WINDOW_NAME}="{AGENT_TTYD_COMMAND}"')


def get_agent_type_from_params(params: dict[str, Any]) -> str | None:
    """Extract the agent type from create command parameters."""
    return params.get("agent_type") or params.get("positional_agent_type")


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface], type[AgentTypeConfig]]:
    """Register the claude-zygote agent type."""
    return ("claude-zygote", ClaudeZygoteAgent, ClaudeAgentConfig)


@hookimpl
def override_command_options(
    command_name: str,
    command_class: type,
    params: dict[str, Any],
) -> None:
    """Add an agent ttyd web terminal when creating claude-zygote agents."""
    if command_name != "create":
        return

    agent_type = get_agent_type_from_params(params)
    if agent_type != "claude-zygote":
        return

    inject_agent_ttyd(params)
