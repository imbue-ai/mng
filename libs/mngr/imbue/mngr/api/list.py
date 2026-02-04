from collections.abc import Callable
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger
from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.thread_utils import ObservableThread
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.pure import pure
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundOnHostError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ProviderInstanceNotFoundError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.agent import AgentStatus
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.interfaces.data_types import SSHInfo
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance
from imbue.mngr.utils.cel_utils import apply_cel_filters_to_context
from imbue.mngr.utils.cel_utils import compile_cel_filters
from imbue.mngr.utils.logging import log_call


class AgentInfo(FrozenModel):
    """Complete information about an agent for listing purposes.

    This combines certified and reported data from the agent with host information.
    """

    id: AgentId = Field(description="Agent ID")
    name: AgentName = Field(description="Agent name")
    type: str = Field(description="Agent type (claude, codex, etc.)")
    command: CommandString = Field(description="Command used to start the agent")
    work_dir: Path = Field(description="Working directory")
    create_time: datetime = Field(description="Creation timestamp")
    start_on_boot: bool = Field(description="Whether agent starts on host boot")

    lifecycle_state: AgentLifecycleState = Field(description="Lifecycle state (stopped/running/replaced/done)")
    status: AgentStatus | None = Field(default=None, description="Current status (reported)")
    url: str | None = Field(default=None, description="Agent URL (reported)")
    start_time: datetime | None = Field(default=None, description="Last start time (reported)")
    runtime_seconds: float | None = Field(default=None, description="Runtime in seconds")
    user_activity_time: datetime | None = Field(default=None, description="Last user activity (reported)")
    agent_activity_time: datetime | None = Field(default=None, description="Last agent activity (reported)")
    ssh_activity_time: datetime | None = Field(default=None, description="Last SSH activity (reported)")
    idle_seconds: float | None = Field(default=None, description="Idle time in seconds")
    idle_mode: str | None = Field(default=None, description="Idle detection mode")

    host: HostInfo = Field(description="Host information")

    plugin: dict[str, Any] = Field(default_factory=dict, description="Plugin-specific fields")


class ErrorInfo(FrozenModel):
    """Information about an error encountered during listing.

    This preserves the exception type and message instead of converting to a string immediately.
    """

    exception_type: str = Field(description="The type name of the exception (e.g., 'RuntimeError')")
    message: str = Field(description="The error message")

    @classmethod
    def build(cls, exception: BaseException) -> "ErrorInfo":
        """Build an ErrorInfo from an exception."""
        return cls(exception_type=type(exception).__name__, message=str(exception))


class ProviderErrorInfo(ErrorInfo):
    """Error information with provider context."""

    provider_name: ProviderInstanceName = Field(description="Name of the provider where the error occurred")

    @classmethod
    def build_for_provider(cls, exception: BaseException, provider_name: ProviderInstanceName) -> "ProviderErrorInfo":
        """Build a ProviderErrorInfo from an exception and provider name."""
        return cls(
            exception_type=type(exception).__name__,
            message=str(exception),
            provider_name=provider_name,
        )


class HostErrorInfo(ErrorInfo):
    """Error information with host context."""

    host_id: HostId = Field(description="ID of the host where the error occurred")

    @classmethod
    def build_for_host(cls, exception: BaseException, host_id: HostId) -> "HostErrorInfo":
        """Build a HostErrorInfo from an exception and host ID."""
        return cls(
            exception_type=type(exception).__name__,
            message=str(exception),
            host_id=host_id,
        )


class AgentErrorInfo(ErrorInfo):
    """Error information with agent context."""

    agent_id: AgentId = Field(description="ID of the agent where the error occurred")

    @classmethod
    def build_for_agent(cls, exception: BaseException, agent_id: AgentId) -> "AgentErrorInfo":
        """Build an AgentErrorInfo from an exception and agent ID."""
        return cls(
            exception_type=type(exception).__name__,
            message=str(exception),
            agent_id=agent_id,
        )


class ListResult(MutableModel):
    """Result of listing agents."""

    agents: list[AgentInfo] = Field(default_factory=list, description="List of agents with their full information")
    errors: list[ErrorInfo] = Field(default_factory=list, description="Errors encountered while listing")


def _get_persisted_agent_data(
    provider: ProviderInstanceInterface,
    host_id: HostId,
    agent_id: AgentId,
) -> dict[str, Any] | None:
    """Get persisted agent data from the provider's volume storage.

    This is used for stopped hosts where we can't SSH to get live agent data.
    Returns the agent data dict or None if not found.
    """
    try:
        agent_records = provider.list_persisted_agent_data_for_host(host_id)
        for agent_data in agent_records:
            if agent_data.get("id") == str(agent_id):
                return agent_data
    except (KeyError, ValueError, OSError) as e:
        logger.trace("Could not get persisted agent data for {}: {}", agent_id, e)

    return None


@log_call
def list_agents(
    mngr_ctx: MngrContext,
    # CEL expressions - only include agents matching these
    include_filters: tuple[str, ...] = (),
    # CEL expressions - exclude agents matching these
    exclude_filters: tuple[str, ...] = (),
    # If specified, only list agents from these providers (NOT IMPLEMENTED YET)
    provider_names: tuple[str, ...] | None = None,
    # How to handle errors (abort or continue)
    error_behavior: ErrorBehavior = ErrorBehavior.ABORT,
    # Optional callback invoked immediately when each agent is found (for streaming)
    on_agent: Callable[[AgentInfo], None] | None = None,
    # Optional callback invoked immediately when each error is encountered (for streaming)
    on_error: Callable[[ErrorInfo], None] | None = None,
) -> ListResult:
    """List all agents with optional filtering."""
    result = ListResult()

    # Compile CEL filters if provided
    # Note: compilation errors always abort - bad filters should never silently continue
    compiled_include_filters: list[Any] = []
    compiled_exclude_filters: list[Any] = []
    if include_filters or exclude_filters:
        logger.debug("Compiling CEL filters")
        compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)
        logger.trace(
            "Compiled {} include and {} exclude filters", len(compiled_include_filters), len(compiled_exclude_filters)
        )

    try:
        # Load all agents grouped by host
        logger.debug("Loading agents from all providers")
        agents_by_host, providers = load_all_agents_grouped_by_host(mngr_ctx, provider_names, include_destroyed=True)
        provider_map = {provider.name: provider for provider in providers}
        logger.trace("Found {} hosts with agents", len(agents_by_host))

        # Process each host and its agents
        for host_ref, agent_refs in agents_by_host.items():
            # Skip hosts with no agents to process
            if not agent_refs:
                continue

            try:
                provider = provider_map.get(host_ref.provider_name)
                if not provider:
                    exception = ProviderInstanceNotFoundError(host_ref.provider_name)
                    if error_behavior == ErrorBehavior.ABORT:
                        raise exception
                    error_info = ProviderErrorInfo.build_for_provider(exception, host_ref.provider_name)
                    result.errors.append(error_info)
                    if on_error:
                        on_error(error_info)
                    continue

                host = provider.get_host(host_ref.host_id)

                # Build SSH info if this is a remote host (only available for online hosts)
                ssh_info: SSHInfo | None = None

                # Host is the implementation of OnlineHostInterface, ie, this host is online
                if isinstance(host, Host):
                    ssh_connection = host._get_ssh_connection_info()
                    if ssh_connection is None:
                        # Default for local hosts
                        host_hostname: str | None = "localhost"
                    else:
                        user, hostname, port, key_path = ssh_connection
                        host_hostname = hostname
                        ssh_info = SSHInfo(
                            user=user,
                            host=hostname,
                            port=port,
                            key_path=key_path,
                            command=f"ssh -i {key_path} -p {port} {user}@{hostname}",
                        )
                    boot_time = host.get_boot_time()
                    uptime_seconds = host.get_uptime_seconds()
                    resource = host.get_provider_resources()
                else:
                    boot_time = None
                    uptime_seconds = None
                    resource = None
                    host_hostname = None

                host_info = HostInfo(
                    id=host.id,
                    name=str(host.get_name()),
                    provider_name=host_ref.provider_name,
                    host=host_hostname,
                    state=host.get_state().value.lower(),
                    image=host.get_image(),
                    tags=host.get_tags(),
                    boot_time=boot_time,
                    uptime_seconds=uptime_seconds,
                    resource=resource,
                    ssh=ssh_info,
                    snapshots=host.get_snapshots(),
                    failure_reason=host.get_failure_reason(),
                    build_log=host.get_build_log(),
                )

                # Get all agents on this host
                agents = None
                if isinstance(host, OnlineHostInterface):
                    agents = host.get_agents()

                for agent_ref in agent_refs:
                    try:
                        # FIXME: consolidate the below code--it's pretty duplicated between the if and the else
                        if agents is None:
                            # Use persisted agent data for stopped hosts
                            agent_data = _get_persisted_agent_data(provider, host.id, agent_ref.agent_id)
                            if agent_data is None:
                                exception = AgentNotFoundOnHostError(agent_ref.agent_id, host_ref.host_id)
                                if error_behavior == ErrorBehavior.ABORT:
                                    raise exception
                                error_info = AgentErrorInfo.build_for_agent(exception, agent_ref.agent_id)
                                result.errors.append(error_info)
                                if on_error:
                                    on_error(error_info)
                                continue

                            # Create minimal AgentInfo from persisted data
                            # Use epoch as fallback for create_time (should always be present)
                            create_time_str = agent_data.get("create_time")
                            create_time = (
                                datetime.fromisoformat(create_time_str)
                                if create_time_str
                                else datetime(1970, 1, 1, tzinfo=timezone.utc)
                            )
                            agent_info = AgentInfo(
                                id=AgentId(agent_data["id"]),
                                name=AgentName(agent_data["name"]),
                                type=agent_data.get("type", "unknown"),
                                command=CommandString(agent_data.get("command", "")),
                                work_dir=Path(agent_data.get("work_dir", "/")),
                                create_time=create_time,
                                start_on_boot=agent_data.get("start_on_boot", False),
                                lifecycle_state=AgentLifecycleState.STOPPED,
                                status=None,
                                url=None,
                                start_time=None,
                                runtime_seconds=None,
                                user_activity_time=None,
                                agent_activity_time=None,
                                ssh_activity_time=None,
                                idle_seconds=None,
                                idle_mode=None,
                                host=host_info,
                                plugin={},
                            )
                        else:
                            # Find the agent in the list for running hosts
                            agent = next((a for a in (agents or []) if a.id == agent_ref.agent_id), None)

                            if agent is None:
                                exception = AgentNotFoundOnHostError(agent_ref.agent_id, host_ref.host_id)
                                if error_behavior == ErrorBehavior.ABORT:
                                    raise exception
                                error_info = AgentErrorInfo.build_for_agent(exception, agent_ref.agent_id)
                                result.errors.append(error_info)
                                if on_error:
                                    on_error(error_info)
                                continue

                            agent_status = agent.get_reported_status()

                            # Get idle_mode from host's activity config
                            activity_config = host.get_activity_config()

                            agent_info = AgentInfo(
                                id=agent.id,
                                name=agent.name,
                                type=str(agent.agent_type),
                                command=agent.get_command(),
                                work_dir=agent.work_dir,
                                create_time=agent.create_time,
                                start_on_boot=agent.get_is_start_on_boot(),
                                lifecycle_state=agent.get_lifecycle_state(),
                                status=agent_status,
                                url=agent.get_reported_url(),
                                start_time=agent.get_reported_start_time(),
                                runtime_seconds=agent.runtime_seconds,
                                user_activity_time=agent.get_reported_activity_time(ActivitySource.USER),
                                agent_activity_time=agent.get_reported_activity_time(ActivitySource.AGENT),
                                ssh_activity_time=agent.get_reported_activity_time(ActivitySource.SSH),
                                idle_seconds=None,
                                idle_mode=activity_config.idle_mode.value.lower(),
                                host=host_info,
                                plugin={},
                            )

                        # Apply CEL filters if provided
                        if compiled_include_filters or compiled_exclude_filters:
                            if not _apply_cel_filters(agent_info, compiled_include_filters, compiled_exclude_filters):
                                continue

                        result.agents.append(agent_info)
                        if on_agent:
                            on_agent(agent_info)

                    except MngrError as e:
                        if error_behavior == ErrorBehavior.ABORT:
                            raise
                        error_info = AgentErrorInfo.build_for_agent(e, agent_ref.agent_id)
                        result.errors.append(error_info)
                        if on_error:
                            on_error(error_info)

            except MngrError as e:
                if error_behavior == ErrorBehavior.ABORT:
                    raise
                error_info = HostErrorInfo.build_for_host(e, host_ref.host_id)
                result.errors.append(error_info)
                if on_error:
                    on_error(error_info)

    except MngrError as e:
        if error_behavior == ErrorBehavior.ABORT:
            raise
        error_info = ErrorInfo.build(e)
        result.errors.append(error_info)
        if on_error:
            on_error(error_info)

    return result


@pure
def _agent_to_cel_context(agent: AgentInfo) -> dict[str, Any]:
    """Convert an AgentInfo object to a CEL-friendly dict.

    Converts the agent into a flat dictionary suitable for CEL evaluation,
    adding computed fields and type information.
    """
    result = agent.model_dump(mode="json")

    # Add computed fields
    result["type"] = "agent"

    # Add age from create_time
    if result.get("create_time"):
        if isinstance(result["create_time"], str):
            created_dt = datetime.fromisoformat(result["create_time"].replace("Z", "+00:00"))
        else:
            created_dt = result["create_time"]
        result["age"] = (datetime.now(timezone.utc) - created_dt).total_seconds()

    # Add runtime_seconds if available
    if result.get("runtime_seconds") is not None:
        result["runtime"] = result["runtime_seconds"]

    # Add idle_seconds if available (computed from activity times)
    if result.get("user_activity_time") or result.get("agent_activity_time"):
        latest_activity = None
        for activity_field in ["user_activity_time", "agent_activity_time", "ssh_activity_time"]:
            activity_time = result.get(activity_field)
            if activity_time:
                if isinstance(activity_time, str):
                    activity_dt = datetime.fromisoformat(activity_time.replace("Z", "+00:00"))
                else:
                    activity_dt = activity_time
                if latest_activity is None or activity_dt > latest_activity:
                    latest_activity = activity_dt
        if latest_activity:
            result["idle"] = (datetime.now(timezone.utc) - latest_activity).total_seconds()

    # Flatten lifecycle_state value
    if result.get("lifecycle_state"):
        if isinstance(result["lifecycle_state"], dict):
            result["state"] = result["lifecycle_state"].get("value", "").lower()
        else:
            result["state"] = str(result["lifecycle_state"]).lower()

    # Normalize host.provider_name to host.provider for consistency
    if result.get("host") and isinstance(result["host"], dict):
        host = result["host"]
        if "provider_name" in host:
            host["provider"] = host.pop("provider_name")

    return result


def _apply_cel_filters(
    agent: AgentInfo,
    include_filters: Sequence[Any],
    exclude_filters: Sequence[Any],
) -> bool:
    """Apply CEL filters to an agent.

    Returns True if the agent should be included (matches all include filters
    and doesn't match any exclude filters).
    """
    context = _agent_to_cel_context(agent)
    return apply_cel_filters_to_context(
        context=context,
        include_filters=include_filters,
        exclude_filters=exclude_filters,
        error_context_description=f"agent {agent.name}",
    )


def _process_provider_for_host_listing(
    provider: BaseProviderInstance,
    agents_by_host: dict[HostReference, list[AgentReference]],
    include_destroyed: bool,
    results_lock: Lock,
    cg: ConcurrencyGroup,
) -> None:
    """Process a single provider and collect its hosts and agents.

    This function is run in a thread by load_all_agents_grouped_by_host.
    Results are merged into the shared agents_by_host dict under the results_lock.
    """
    logger.trace("Loading hosts from provider {}", provider.name)
    hosts = provider.list_hosts(include_destroyed=include_destroyed, cg=cg)

    # Collect results for this provider
    provider_results: dict[HostReference, list[AgentReference]] = {}
    for host in hosts:
        host_ref = HostReference(
            host_id=host.id,
            host_name=host.get_name(),
            provider_name=provider.name,
        )
        agent_refs = host.get_agent_references()
        provider_results[host_ref] = agent_refs

    # Merge results into the main dict under lock
    with results_lock:
        agents_by_host.update(provider_results)


@log_call
def load_all_agents_grouped_by_host(
    mngr_ctx: MngrContext, provider_names: tuple[str, ...] | None = None, include_destroyed: bool = False
) -> tuple[dict[HostReference, list[AgentReference]], list[BaseProviderInstance]]:
    """Load all agents from all providers, grouped by their host.

    Uses ConcurrencyGroup to query providers in parallel for better performance.
    Handles both online hosts (which can be queried directly) and offline hosts (which use persisted data).
    """
    agents_by_host: dict[HostReference, list[AgentReference]] = {}
    results_lock = Lock()

    logger.debug("Loading all agents from all providers")
    providers = get_all_provider_instances(mngr_ctx, provider_names)
    logger.trace("Found {} provider instances", len(providers))

    # Process all providers in parallel using ConcurrencyGroup
    with ConcurrencyGroup(name="load_all_agents_grouped_by_host") as cg:
        threads: list[ObservableThread] = []
        for provider in providers:
            threads.append(
                cg.start_new_thread(
                    target=_process_provider_for_host_listing,
                    args=(provider, agents_by_host, include_destroyed, results_lock, cg),
                    name=f"load_hosts_{provider.name}",
                )
            )
        for thread in threads:
            thread.join()

    return (agents_by_host, providers)
