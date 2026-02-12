from __future__ import annotations

from imbue.mngr import hookimpl
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.interfaces.agent import AgentInterface


class CodeGuardianAgentConfig(ClaudeAgentConfig):
    """Config for the code-guardian agent type.

    Inherits all Claude agent defaults. The code-guardian agent type is designed
    to be used by the changelings system for automated codebase health reports.
    """


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the code-guardian agent type."""
    return ("code-guardian", ClaudeAgent, CodeGuardianAgentConfig)
