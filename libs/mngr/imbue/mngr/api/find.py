from pathlib import Path
from typing import cast

import deal
from loguru import logger
from pydantic import Field
from pyinfra.api.exceptions import ConnectError

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import HostConnectionError
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import UserInputError
from imbue.mngr.hosts.host import Host
from imbue.mngr.hosts.host import HostLocation
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import LOCAL_PROVIDER_NAME
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance
from imbue.mngr.utils.logging import log_call


class ParsedSourceLocation(FrozenModel):
    """Parsed components of a source location string."""

    agent: str | None = Field(description="Agent ID or name")
    host: str | None = Field(description="Host ID or name")
    path: str | None = Field(description="File path")


@deal.has()
def parse_source_string(
    source: str | None,
    source_agent: str | None = None,
    source_host: str | None = None,
    source_path: str | None = None,
) -> ParsedSourceLocation:
    """Parse source location string into components.

    source format: [AGENT | AGENT.HOST[.PROVIDER] | AGENT.HOST[.PROVIDER]:PATH | HOST[.PROVIDER]:PATH | PATH]

    Everything after the first ':' is treated as the path (to handle colons in paths).
    HOST can optionally include .PROVIDER suffix (e.g., myhost.docker).

    Raises UserInputError if both source and individual parameters are specified.
    """
    if source is not None:
        if source_agent is not None or source_path is not None or source_host is not None:
            raise UserInputError("Specify either --source or the individual source parameters, not both.")

        parsed_agent: str | None = None
        parsed_host: str | None = None
        parsed_path: str | None = None

        if ":" in source:
            prefix, path_part = source.split(":", 1)
            parsed_path = path_part
            if "." in prefix:
                agent_part, host_part = prefix.split(".", 1)
                parsed_agent = agent_part
                parsed_host = host_part
            elif prefix:
                parsed_host = prefix
            else:
                # Empty prefix before colon (e.g., ":path") - no agent or host
                pass
        else:
            if source.startswith(("/", "./", "~/", "../")):
                parsed_path = source
            elif "." in source:
                agent_part, host_part = source.split(".", 1)
                parsed_agent = agent_part
                parsed_host = host_part
            else:
                parsed_agent = source

        source_agent = parsed_agent
        source_host = parsed_host
        source_path = parsed_path

    return ParsedSourceLocation(
        agent=source_agent,
        host=source_host,
        path=source_path,
    )


@deal.has()
def determine_resolved_path(
    parsed_path: str | None,
    resolved_agent: AgentReference | None,
    agent_work_dir_if_available: Path | None,
) -> Path:
    """Determine the final path from parsed components.

    Pure function that determines which path to use based on what's available.
    Raises UserInputError if path cannot be determined.
    """
    if parsed_path is not None:
        return Path(parsed_path)
    if resolved_agent is not None and agent_work_dir_if_available is not None:
        return agent_work_dir_if_available
    if resolved_agent is not None:
        raise UserInputError(f"Could not find agent {resolved_agent.agent_id} on host")
    raise UserInputError("Must specify a path if no agent is specified")


@deal.has()
def resolve_host_reference(
    host_identifier: str | None,
    all_hosts: list[HostReference],
) -> HostReference | None:
    """Resolve a host identifier (ID or name) to a HostReference.

    Returns None if host_identifier is None.
    Raises UserInputError if host cannot be found or multiple hosts match the name.
    """
    if host_identifier is None:
        return None

    try:
        host_id = HostId(host_identifier)
        resolved_host = get_host_from_list_by_id(host_id, all_hosts)
    except ValueError:
        host_name = HostName(host_identifier)
        resolved_host = get_unique_host_from_list_by_name(host_name, all_hosts)

    if resolved_host is None:
        raise UserInputError(f"Could not find host with ID or name: {host_identifier}")

    return resolved_host


@deal.has()
def resolve_agent_reference(
    agent_identifier: str | None,
    resolved_host: HostReference | None,
    agents_by_host: dict[HostReference, list[AgentReference]],
) -> tuple[HostReference, AgentReference] | None:
    """Resolve an agent identifier (ID or name) to host and agent references.

    Returns None if agent_identifier is None.
    Raises UserInputError if agent cannot be found or multiple agents match.
    """
    if agent_identifier is None:
        return None

    matching_agents: list[tuple[HostReference, AgentReference]] = []

    for host_ref, agent_refs in agents_by_host.items():
        if resolved_host is not None and host_ref.host_id != resolved_host.host_id:
            continue

        for agent_ref in agent_refs:
            try:
                agent_id = AgentId(agent_identifier)
                if agent_ref.agent_id == agent_id:
                    matching_agents.append((host_ref, agent_ref))
            except ValueError:
                agent_name = AgentName(agent_identifier)
                if agent_ref.agent_name == agent_name:
                    matching_agents.append((host_ref, agent_ref))

    if len(matching_agents) == 0:
        raise UserInputError(f"Could not find agent with ID or name: {agent_identifier}")
    elif len(matching_agents) > 1:
        raise UserInputError(f"Multiple agents found with ID or name: {agent_identifier}")
    else:
        return matching_agents[0]


@log_call
def resolve_source_location(
    source: str | None,
    source_agent: str | None,
    source_host: str | None,
    source_path: str | None,
    agents_by_host: dict[HostReference, list[AgentReference]],
    mngr_ctx: MngrContext,
) -> HostLocation:
    """Parse and resolve source location to a concrete host and path.

    source format: [AGENT | AGENT.HOST[.PROVIDER] | AGENT.HOST[.PROVIDER]:PATH | HOST[.PROVIDER]:PATH | PATH]

    Everything after the first ':' is treated as the path (to handle colons in paths).
    HOST can optionally include .PROVIDER suffix (e.g., myhost.docker).

    This is useful because it allows the user to specify the source agent / location in a maximally flexible way.
    This is important for making the CLI easy to use in a variety of scenarios.
    """
    # Parse the source string into components
    logger.debug("Parsing source location")
    parsed = parse_source_string(source, source_agent, source_host, source_path)
    logger.trace("Parsed source: agent={} host={} path={}", parsed.agent, parsed.host, parsed.path)

    # Resolve host and agent references from the parsed components
    all_hosts = list(agents_by_host.keys())
    logger.debug("Resolving host reference")
    resolved_host = resolve_host_reference(parsed.host, all_hosts)
    logger.debug("Resolving agent reference")
    agent_result = resolve_agent_reference(parsed.agent, resolved_host, agents_by_host)

    # Extract resolved agent if found
    resolved_agent: AgentReference | None = None
    if agent_result is not None:
        resolved_host, resolved_agent = agent_result

    # Get the host interface from the provider
    logger.debug("Getting host interface from provider")
    if resolved_host is None:
        provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), mngr_ctx)
        host_interface = provider.get_host(HostName("local"))
    else:
        provider = get_provider_instance(resolved_host.provider_name, mngr_ctx)
        host_interface = provider.get_host(resolved_host.host_id)
    logger.trace("Resolved to host id={}", host_interface.id)

    # Ensure host is online for file operations
    if not isinstance(host_interface, OnlineHostInterface):
        raise HostOfflineError(f"Host '{host_interface.id}' is offline. Start the host first.")

    # Resolve the final path
    agent_work_dir: Path | None = None
    if resolved_agent is not None:
        for agent in host_interface.get_agents():
            if agent.id == resolved_agent.agent_id:
                agent_work_dir = agent.work_dir
                break

    resolved_path = determine_resolved_path(
        parsed_path=parsed.path,
        resolved_agent=resolved_agent,
        agent_work_dir_if_available=agent_work_dir,
    )

    return HostLocation(
        host=host_interface,
        path=resolved_path,
    )


@deal.has()
def get_host_from_list_by_id(host_id: HostId, all_hosts: list[HostReference]) -> HostReference | None:
    for host in all_hosts:
        if host.host_id == host_id:
            return host
    return None


@deal.has()
def get_unique_host_from_list_by_name(host_name: HostName, all_hosts: list[HostReference]) -> HostReference | None:
    matching_hosts = [host for host in all_hosts if host.host_name == host_name]
    if len(matching_hosts) == 1:
        return matching_hosts[0]
    elif len(matching_hosts) > 1:
        raise UserInputError(f"Multiple hosts found with name: {host_name}")
    else:
        return None


def _ensure_host_started(host: HostInterface, is_start_desired: bool, provider: BaseProviderInstance) -> Host:
    """Ensure the host is online and started.

    If the host is already online, returns it cast to OnlineHostInterface.
    If offline and start is desired, starts the host and returns the online host.
    If offline and start is not desired, raises UserInputError.
    """
    # Check using is_online attribute (works with both real hosts and mocks)
    if host.is_online:
        return cast(Host, host)
    if is_start_desired:
        logger.info("Host is offline, starting it...", host_id=host.id, provider=provider.name)
        started_host = provider.start_host(host)
        return started_host
    else:
        raise UserInputError(
            f"Host '{host.id}' is offline and --no-start was specified. Use --start to automatically start the host."
        )


def _ensure_agent_started(agent: AgentInterface, host: OnlineHostInterface, is_start_desired: bool) -> None:
    # Check if the agent's tmux session exists and start it if needed
    lifecycle_state = agent.get_lifecycle_state()
    if lifecycle_state != AgentLifecycleState.RUNNING:
        if is_start_desired:
            logger.info("Agent {} is stopped, starting it", agent.name)
            host.start_agents([agent.id])
        else:
            raise UserInputError(
                f"Agent '{agent.name}' is stopped and --no-start was specified. "
                "Use --start to automatically start the agent."
            )


@log_call
def find_and_maybe_start_agent_by_name_or_id(
    agent_str: str,
    agents_by_host: dict[HostReference, list[AgentReference]],
    mngr_ctx: MngrContext,
    command_name: str,
    is_start_desired: bool = False,
) -> tuple[AgentInterface, OnlineHostInterface]:
    """Find an agent by name or ID and return the agent and host interfaces.

    This function resolves an agent identifier to the actual agent and host objects,
    which is needed by CLI commands that need to interact with the agent.

    Raises AgentNotFoundError if the agent cannot be found by ID.
    Raises UserInputError if the agent cannot be found by name or if multiple agents match.
    """
    # Try parsing as an AgentId first
    try:
        agent_id = AgentId(agent_str)
    except ValueError:
        agent_id = None

    if agent_id is not None:
        for host_ref, agent_refs in agents_by_host.items():
            for agent_ref in agent_refs:
                if agent_ref.agent_id == agent_id:
                    provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                    host = provider.get_host(host_ref.host_id)
                    online_host = _ensure_host_started(host, is_start_desired, provider)
                    for agent in online_host.get_agents():
                        if agent.id == agent_id:
                            _ensure_agent_started(agent, online_host, is_start_desired)
                            return agent, online_host
        raise AgentNotFoundError(agent_id)

    # Try matching by name
    agent_name = AgentName(agent_str)
    matching: list[tuple[AgentInterface, OnlineHostInterface]] = []

    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            if agent_ref.agent_name == agent_name:
                provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
                host = provider.get_host(host_ref.host_id)
                online_host = _ensure_host_started(host, is_start_desired, provider)
                # Find the specific agent by ID (not name, to avoid duplicates)
                for agent in online_host.get_agents():
                    if agent.id == agent_ref.agent_id:
                        matching.append((agent, online_host))
                        break

    if not matching:
        raise UserInputError(f"No agent found with name or ID: {agent_str}")

    if len(matching) > 1:
        # Build helpful error message showing the matching agents
        agent_list = "\n".join([f"  - {agent.id} (on {host.connector.name})" for agent, host in matching])
        raise UserInputError(
            f"Multiple agents found with name '{agent_str}':\n{agent_list}\n\n"
            f"Please use the agent ID instead:\n"
            f"  mngr {command_name} <agent-id>\n\n"
            f"To see all agent IDs, run:\n"
            f"  mngr list --fields id,name,host"
        )

    # make sure the agent is started
    agent, host = matching[0]
    _ensure_agent_started(agent, host, is_start_desired)

    return agent, host


@log_call
def load_all_agents_grouped_by_host(mngr_ctx: MngrContext) -> dict[HostReference, list[AgentReference]]:
    """Load all agents from all providers, grouped by their host.

    Loops through all providers, gets all hosts from each provider, and then gets all agents for each host.
    Handles both online hosts (which can be queried directly) and offline hosts (which use persisted data).
    """
    agents_by_host: dict[HostReference, list[AgentReference]] = {}

    logger.debug("Loading all agents from all providers")
    providers = get_all_provider_instances(mngr_ctx)
    logger.trace("Found {} provider instances", len(providers))

    for provider in providers:
        logger.trace("Loading hosts from provider {}", provider.name)
        hosts = provider.list_hosts(include_destroyed=False)

        for host in hosts:
            # For offline hosts, get agent references from persisted data
            if not isinstance(host, OnlineHostInterface):
                agent_refs = host.get_agent_references()
                if agent_refs:
                    # Use first agent ref's info to build host reference
                    host_ref = HostReference(
                        host_id=host.id,
                        host_name=HostName(str(host.id)),
                        provider_name=provider.name,
                    )
                    agents_by_host[host_ref] = agent_refs
                continue

            # Host is online - cast to OnlineHostInterface
            online_host = cast(OnlineHostInterface, host)
            host_ref = HostReference(
                host_id=host.id,
                host_name=HostName(online_host.connector.name),
                provider_name=provider.name,
            )

            # Try to get agents from the host. For stopped/unreachable hosts,
            # connection will fail - try to get persisted agent data from volume.
            try:
                agents = online_host.get_agents()
                agent_refs = [
                    AgentReference(
                        host_id=host.id,
                        agent_id=agent.id,
                        agent_name=agent.name,
                        provider_name=provider.name,
                    )
                    for agent in agents
                ]
            except (ConnectError, HostConnectionError, OSError) as e:
                logger.trace("Could not get agents from host {} (may be stopped): {}", host.id, e)
                # Try to get persisted agent data from the provider (for stopped hosts)
                agent_refs = []
                try:
                    agent_records = provider.list_persisted_agent_data_for_host(host.id)
                    for agent_data in agent_records:
                        agent_refs.append(
                            AgentReference(
                                host_id=host.id,
                                agent_id=AgentId(agent_data["id"]),
                                agent_name=AgentName(agent_data["name"]),
                                provider_name=provider.name,
                            )
                        )
                    logger.trace("Loaded {} persisted agents for stopped host {}", len(agent_refs), host.id)
                except (KeyError, ValueError) as inner_e:
                    logger.trace("Could not load persisted agents for host {}: {}", host.id, inner_e)

            agents_by_host[host_ref] = agent_refs

    return agents_by_host
