import tempfile
from pathlib import Path

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import AgentEnvironmentOptions
from imbue.mngr.interfaces.host import AgentProvisioningOptions
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface


def _read_existing_env_content(host: OnlineHostInterface, agent: AgentInterface) -> str | None:
    """Read the agent's existing env file content from the host.

    Returns the file content, or None if the env file does not exist.
    Uses host.read_text_file() so this works for both local and remote hosts.
    """
    env_path = host.get_agent_env_path(agent)
    try:
        return host.read_text_file(env_path)
    except FileNotFoundError:
        return None


def provision_agent(
    agent: AgentInterface,
    host: OnlineHostInterface,
    provisioning: AgentProvisioningOptions,
    environment: AgentEnvironmentOptions,
    mngr_ctx: MngrContext,
) -> None:
    """Re-run provisioning on an existing agent.

    Reads the agent's existing env file from the host (using host.read_text_file so
    it works for both local and remote hosts), then includes it as the first env_file
    entry so existing vars are preserved with lowest priority. CLI-provided env_files
    and env_vars override them.

    Precedence (lowest to highest): existing env vars < CLI env_files < CLI env_vars.
    """
    # Read existing env content from the host (handles both local and remote)
    existing_env_content = _read_existing_env_content(host, agent)

    if existing_env_content is not None:
        # Write to a local temp file so _collect_agent_env_vars can read it
        # as the first env_file (giving it lowest priority among user-provided values)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
            existing_env_local_path = Path(tmp.name)
            tmp.write(existing_env_content)

        merged_env_files = (existing_env_local_path,) + environment.env_files
    else:
        merged_env_files = environment.env_files

    merged_environment = AgentEnvironmentOptions(
        env_vars=environment.env_vars,
        env_files=merged_env_files,
    )

    # Build CreateAgentOptions with defaults for all creation-only fields
    options = CreateAgentOptions(
        provisioning=provisioning,
        environment=merged_environment,
    )

    try:
        with host.lock_cooperatively():
            with log_span("Provisioning agent {}", agent.name):
                host.provision_agent(agent, options, mngr_ctx)
    finally:
        # Clean up the temp file if we created one
        if existing_env_content is not None:
            existing_env_local_path.unlink(missing_ok=True)

    logger.info("Provisioned agent: {}", agent.name)
