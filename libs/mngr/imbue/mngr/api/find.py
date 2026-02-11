from collections.abc import Callable
from pathlib import Path
from typing import assert_never

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mngr.api.list import list_agents
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundError
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


class ParsedSourceLocation(FrozenModel):
    """Parsed components of a source location string."""

    agent: str | None = Field(description="Agent ID or name")
    host: str | None = Field(description="Host ID or name")
    path: str | None = Field(description="File path")


@pure
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


@pure
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


@pure
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


@pure
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
    with log_span("Parsing source location"):
        parsed = parse_source_string(source, source_agent, source_host, source_path)
        logger.trace("Parsed source: agent={} host={} path={}", parsed.agent, parsed.host, parsed.path)

    # Resolve host and agent references from the parsed components
    all_hosts = list(agents_by_host.keys())
    with log_span("Resolving host reference"):
        resolved_host = resolve_host_reference(parsed.host, all_hosts)
    with log_span("Resolving agent reference"):
        agent_result = resolve_agent_reference(parsed.agent, resolved_host, agents_by_host)

    # Extract resolved agent if found
    resolved_agent: AgentReference | None = None
    if agent_result is not None:
        resolved_host, resolved_agent = agent_result

    # Get the host interface from the provider
    with log_span("Getting host interface from provider"):
        if resolved_host is None:
            provider = get_provider_instance(ProviderInstanceName(LOCAL_PROVIDER_NAME), mngr_ctx)
            host_interface = provider.get_host(HostName("local"))
        else:
            provider = get_provider_instance(resolved_host.provider_name, mngr_ctx)
            host_interface = provider.get_host(resolved_host.host_id)

    # Ensure host is online for file operations
    if not isinstance(host_interface, OnlineHostInterface):
        raise HostOfflineError(f"Host '{host_interface.id}' is offline. Start the host first.")

    # Resolve the final path
    agent_work_dir: Path | None = None
    if resolved_agent is not None:
        for agent_ref in host_interface.get_agent_references():
            if agent_ref.agent_id == resolved_agent.agent_id:
                agent_work_dir = agent_ref.work_dir
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


@pure
def get_host_from_list_by_id(host_id: HostId, all_hosts: list[HostReference]) -> HostReference | None:
    for host in all_hosts:
        if host.host_id == host_id:
            return host
    return None


@pure
def get_unique_host_from_list_by_name(host_name: HostName, all_hosts: list[HostReference]) -> HostReference | None:
    matching_hosts = [host for host in all_hosts if host.host_name == host_name]
    if len(matching_hosts) == 1:
        return matching_hosts[0]
    elif len(matching_hosts) > 1:
        raise UserInputError(f"Multiple hosts found with name: {host_name}")
    else:
        return None


def ensure_host_started(
    host: HostInterface, is_start_desired: bool, provider: BaseProviderInstance
) -> tuple[Host, bool]:
    """Ensure the host is online and started.

    If the host is already online, returns it cast to OnlineHostInterface.
    If offline and start is desired, starts the host and returns the online host.
    If offline and start is not desired, raises UserInputError.

    Also returns a boolean indicating whether the host was started.
    """
    match host:
        case Host() as online_host:
            return online_host, False
        case HostInterface() as offline_host:
            if is_start_desired:
                logger.info("Host is offline, starting it...", host_id=offline_host.id, provider=provider.name)
                started_host = provider.start_host(offline_host)
                return started_host, True
            else:
                raise UserInputError(
                    f"Host '{offline_host.id}' is offline and --no-start was specified. Use --start to automatically start the host."
                )
        case _ as unreachable:
            assert_never(unreachable)


def ensure_agent_started(agent: AgentInterface, host: OnlineHostInterface, is_start_desired: bool) -> None:
    """Ensure an agent is started, starting it if needed and desired.

    If the agent is stopped and is_start_desired is True, starts the agent.
    If the agent is stopped and is_start_desired is False, raises UserInputError.
    """
    # Check if the agent's tmux session exists and start it if needed
    lifecycle_state = agent.get_lifecycle_state()
    if lifecycle_state not in (AgentLifecycleState.RUNNING, AgentLifecycleState.REPLACED, AgentLifecycleState.WAITING):
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
    get_provider: Callable[[ProviderInstanceName, MngrContext], BaseProviderInstance] | None = None,
) -> tuple[AgentInterface, OnlineHostInterface]:
    """Find an agent by name or ID and return the agent and host interfaces.

    This function resolves an agent identifier to the actual agent and host objects,
    which is needed by CLI commands that need to interact with the agent.

    Raises AgentNotFoundError if the agent cannot be found by ID.
    Raises UserInputError if the agent cannot be found by name or if multiple agents match.
    """
    resolve_provider = get_provider if get_provider is not None else get_provider_instance

    # Try parsing as an AgentId first
    try:
        agent_id = AgentId(agent_str)
    except ValueError:
        agent_id = None

    if agent_id is not None:
        for host_ref, agent_refs in agents_by_host.items():
            for agent_ref in agent_refs:
                if agent_ref.agent_id == agent_id:
                    provider = resolve_provider(host_ref.provider_name, mngr_ctx)
                    host = provider.get_host(host_ref.host_id)
                    online_host, _was_started = ensure_host_started(host, is_start_desired, provider)
                    for agent in online_host.get_agents():
                        if agent.id == agent_id:
                            ensure_agent_started(agent, online_host, is_start_desired)
                            return agent, online_host
        raise AgentNotFoundError(agent_id)

    # Try matching by name
    agent_name = AgentName(agent_str)
    matching: list[tuple[AgentInterface, OnlineHostInterface]] = []

    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            if agent_ref.agent_name == agent_name:
                provider = resolve_provider(host_ref.provider_name, mngr_ctx)
                host = provider.get_host(host_ref.host_id)
                online_host, _was_started = ensure_host_started(host, is_start_desired, provider)
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
    ensure_agent_started(agent, host, is_start_desired)

    return agent, host


class AgentMatch(FrozenModel):
    """Information about an agent that matched a search query."""

    agent_id: AgentId
    agent_name: AgentName
    host_id: HostId
    provider_name: ProviderInstanceName


@pure
def find_agents_by_identifiers_or_state(
    agent_identifiers: list[str],
    filter_all: bool,
    target_state: AgentLifecycleState,
    mngr_ctx: MngrContext,
) -> list[AgentMatch]:
    """Find agents matching identifiers or a target lifecycle state.

    When filter_all is True, returns all agents in the target_state.
    When filter_all is False, returns agents matching the given identifiers
    (by name or ID).

    Raises AgentNotFoundError if any identifier does not match an agent.
    """

    matches: list[AgentMatch] = []
    matched_identifiers: set[str] = set()

    for agent_ref in list_agents(mngr_ctx).agents:
        should_include: bool
        if filter_all:
            should_include = agent_ref.state == target_state
        elif agent_identifiers:
            agent_name_str = str(agent_ref.name)
            agent_id_str = str(agent_ref.id)

            should_include = False
            for identifier in agent_identifiers:
                if identifier == agent_name_str or identifier == agent_id_str:
                    should_include = True
                    matched_identifiers.add(identifier)
        else:
            should_include = False

        if should_include:
            matches.append(
                AgentMatch(
                    agent_id=agent_ref.id,
                    agent_name=agent_ref.name,
                    host_id=agent_ref.host.id,
                    provider_name=agent_ref.host.provider_name,
                )
            )

    # Verify all specified identifiers were found
    if agent_identifiers:
        unmatched_identifiers = set(agent_identifiers) - matched_identifiers
        if unmatched_identifiers:
            unmatched_list = ", ".join(sorted(unmatched_identifiers))
            raise AgentNotFoundError(f"No agent(s) found matching: {unmatched_list}")

    return matches


@pure
def group_agents_by_host(agents: list[AgentMatch]) -> dict[str, list[AgentMatch]]:
    """Group a list of AgentMatch objects by their host.

    Returns a dictionary where keys are "{host_id}:{provider_name}" and
    values are lists of AgentMatch objects on that host.
    """
    agents_by_host: dict[str, list[AgentMatch]] = {}
    for match in agents:
        key = f"{match.host_id}:{match.provider_name}"
        if key not in agents_by_host:
            agents_by_host[key] = []
        agents_by_host[key].append(match)
    return agents_by_host
