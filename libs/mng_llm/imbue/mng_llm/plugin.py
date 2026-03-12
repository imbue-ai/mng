"""LLM agent plugin for mng.

Provides the ``llm`` agent type which runs the ``llm`` CLI tool as a managed
agent. Includes provisioning for the llm toolchain, conversation management,
and supporting service infrastructure (chat, web UI, conversation watcher).
"""

from __future__ import annotations

from collections.abc import Sequence

import click
from pydantic import Field

from imbue.mng import hookimpl
from imbue.mng.agents.base_agent import BaseAgent
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import CreateAgentOptions
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.primitives import CommandString
from imbue.mng_llm.provisioning import configure_llm_user_path
from imbue.mng_llm.provisioning import create_mind_conversations_table
from imbue.mng_llm.provisioning import install_llm_toolchain
from imbue.mng_llm.provisioning import provision_llm_tools
from imbue.mng_llm.provisioning import provision_supporting_services
from imbue.mng_llm.settings import load_settings_from_host


class LlmAgentConfig(AgentTypeConfig):
    """Config for the llm agent type.

    Configures how the llm CLI tool is set up and run as a managed agent.
    """

    command: CommandString = Field(
        default=CommandString("llm"),
        description="The command to run for this agent type.",
    )
    install_llm: bool = Field(
        default=True,
        description="Whether to install llm and its plugins (llm-anthropic, llm-live-chat) during provisioning.",
    )

    def merge_with(self, override: AgentTypeConfig) -> AgentTypeConfig:
        """Merge this config with an override config.

        Scalar fields from the override take precedence when not None.
        """
        if not isinstance(override, LlmAgentConfig):
            return override

        merged_command = self.command
        if hasattr(override, "command") and override.command is not None:
            merged_command = override.command

        return self.__class__(
            command=merged_command,
            install_llm=override.install_llm,
            cli_args=override.cli_args or self.cli_args,
            permissions=override.permissions or self.permissions,
        )


class LlmAgent(BaseAgent):
    """Agent class for running the llm CLI tool.

    Extends BaseAgent with llm-specific provisioning:
    - Installs the llm toolchain (llm, llm-anthropic, llm-live-chat)
    - Configures per-agent llm data directory (LLM_USER_PATH)
    - Creates the mind_conversations table for conversation metadata
    - Provisions chat scripts and llm tool functions
    """

    def _get_llm_config(self) -> LlmAgentConfig:
        """Get the llm-specific config from this agent.

        Raises RuntimeError if the agent config is not an LlmAgentConfig,
        which indicates a misconfiguration in the agent type registration.
        """
        if not isinstance(self.agent_config, LlmAgentConfig):
            raise RuntimeError(
                f"LlmAgent requires LlmAgentConfig, got {type(self.agent_config).__name__}. "
                "This indicates the agent type was registered with the wrong config class."
            )
        return self.agent_config

    def modify_env_vars(
        self,
        host: OnlineHostInterface,
        env_vars: dict[str, str],
    ) -> None:
        """Set UV_TOOL_DIR and UV_TOOL_BIN_DIR for per-agent tool isolation.

        These env vars ensure that ``uv tool install`` (run by the
        mng_recursive plugin) places the mng binary and its venv into
        the agent's state directory, and that any subsequent ``uv tool``
        invocations within the agent's processes also use the same paths.
        """
        agent_state_dir = env_vars.get("MNG_AGENT_STATE_DIR", "")
        if agent_state_dir:
            bin_dir = f"{agent_state_dir}/bin"
            env_vars["UV_TOOL_DIR"] = f"{agent_state_dir}/tools"
            env_vars["UV_TOOL_BIN_DIR"] = bin_dir

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mng_ctx: MngContext,
    ) -> None:
        """Provision an llm agent with toolchain and conversation infrastructure.

        Steps:
        1. Per-agent mng installation (via mng_recursive)
        2. llm + plugin installation
        3. Per-agent llm data directory
        4. Conversations table in llm database
        5. Supporting service scripts (chat, ttyd dispatch)
        6. LLM tool functions (context gathering for conversations)
        """
        from imbue.mng_recursive.provisioning import provision_mng_for_agent

        provision_mng_for_agent(agent=self, host=host, mng_ctx=mng_ctx)

        settings = load_settings_from_host(host, self.work_dir)
        provisioning = settings.provisioning
        config = self._get_llm_config()

        if config.install_llm:
            install_llm_toolchain(host, provisioning)

        agent_state_dir = self._get_agent_dir()

        configure_llm_user_path(host, agent_state_dir, provisioning)
        create_mind_conversations_table(host, agent_state_dir, provisioning)
        provision_supporting_services(host, agent_state_dir, provisioning)
        provision_llm_tools(host, agent_state_dir, provisioning)


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register llm supporting service commands with mng."""
    from imbue.mng_llm.cli import get_all_commands

    return get_all_commands()


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface], type[AgentTypeConfig]]:
    """Register the llm agent type."""
    return ("llm", LlmAgent, LlmAgentConfig)
