from pathlib import Path

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import AgentEnvironmentOptions
from imbue.mngr.interfaces.host import AgentProvisioningOptions
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface


def provision_agent(
    agent: AgentInterface,
    host: OnlineHostInterface,
    provisioning: AgentProvisioningOptions,
    environment: AgentEnvironmentOptions,
    mngr_ctx: MngrContext,
) -> None:
    """Re-run provisioning on an existing agent.

    Constructs a CreateAgentOptions with defaults for re-provisioning, preserving
    the agent's existing env file as the first env_files entry so that previously-
    stored env vars (including GIT_BASE_BRANCH) are preserved. New CLI-provided
    env_vars and env_files override them.
    """
    # Read the agent's existing env file path so we can preserve its vars
    host_impl = _as_host(host)
    existing_env_path = host_impl.get_agent_env_path(agent)

    # Prepend the existing env file to env_files so stored vars are loaded first,
    # then CLI-provided env_files and env_vars override them
    merged_env_files: tuple[Path, ...]
    if existing_env_path.exists():
        merged_env_files = (existing_env_path,) + environment.env_files
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

    with host.lock_cooperatively():
        with log_span("Provisioning agent {}", agent.name):
            host.provision_agent(agent, options, mngr_ctx)

    logger.info("Provisioned agent: {}", agent.name)


def _as_host(host: OnlineHostInterface) -> Host:
    """Cast an OnlineHostInterface to the concrete Host implementation.

    This is needed to access get_agent_env_path which lives on the Host class
    rather than the interface.
    """
    if not isinstance(host, Host):
        raise TypeError(f"Expected Host instance, got {type(host).__name__}")
    return host
