"""Coder agent type: a Claude agent that provisions the autofix skill."""

from __future__ import annotations

from imbue.mng import hookimpl
from imbue.mng.agents.default_plugins.autofix_skill import install_autofix_skill_locally
from imbue.mng.agents.default_plugins.autofix_skill import install_autofix_skill_remotely
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import CreateAgentOptions
from imbue.mng.interfaces.host import OnlineHostInterface


class CoderAgentConfig(ClaudeAgentConfig):
    """Config for the coder agent type."""


class CoderAgent(ClaudeAgent):
    """Agent that extends Claude with the autofix skill.

    The autofix skill allows automated code review and fixing via stop hooks.
    It is installed during provisioning so it is available when invoked via
    ``/autofix`` in a reviewer window.
    """

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mng_ctx: MngContext,
    ) -> None:
        """Run standard Claude provisioning, then install the autofix skill."""
        super().provision(host, options, mng_ctx)

        if host.is_local:
            install_autofix_skill_locally(mng_ctx)
        else:
            install_autofix_skill_remotely(host)


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the coder agent type."""
    return ("coder", CoderAgent, CoderAgentConfig)
