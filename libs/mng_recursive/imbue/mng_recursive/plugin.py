"""Plugin registration for mng_recursive."""

import json
import os
from typing import Any

from imbue.mng import hookimpl
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.plugin_registry import register_plugin_config
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng_recursive.data_types import RecursivePluginConfig
from imbue.mng_recursive.provisioning import provision_mng_on_host

register_plugin_config("recursive", RecursivePluginConfig)


def _get_chain_of_command() -> list[str]:
    """Read the current chain of command from the MNG_CHAIN_OF_COMMAND env var.

    Returns an empty list if the env var is not set or is empty.
    """
    raw = os.environ.get("MNG_CHAIN_OF_COMMAND", "")
    if not raw:
        return []
    return json.loads(raw)


@hookimpl
def override_command_options(
    command_name: str,
    command_class: type,
    params: dict[str, Any],
) -> None:
    """Set chain-of-command labels and env var when creating agents from within an agent."""
    if command_name != "create":
        return

    commanding_agent_id = os.environ.get("MNG_AGENT_ID")
    if not commanding_agent_id:
        return

    # Build the new chain of command by appending the current agent's ID
    current_chain = _get_chain_of_command()
    new_chain = [*current_chain, commanding_agent_id]
    chain_json = json.dumps(new_chain)

    # Add labels
    existing_labels: tuple[str, ...] = params.get("label", ())
    params["label"] = (
        *existing_labels,
        f"commanding_agent_id={commanding_agent_id}",
        f"chain_of_command={chain_json}",
    )

    # Add the MNG_CHAIN_OF_COMMAND env var so nested agents can extend the chain
    existing_env: tuple[str, ...] = params.get("agent_env", ())
    params["agent_env"] = (*existing_env, f"MNG_CHAIN_OF_COMMAND={chain_json}")


@hookimpl
def on_after_provisioning(agent: AgentInterface, host: OnlineHostInterface, mng_ctx: MngContext) -> None:
    """Inject mng config, settings, and dependencies into remote hosts after provisioning."""
    provision_mng_on_host(host=host, mng_ctx=mng_ctx)
