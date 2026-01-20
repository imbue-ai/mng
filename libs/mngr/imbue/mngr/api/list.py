from collections.abc import Callable
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import deal
from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.find import load_all_agents_grouped_by_host
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundOnHostError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ProviderInstanceNotFoundError
from imbue.mngr.interfaces.agent import AgentStatus
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName
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

    if provider_names:
        raise NotImplementedError("Provider filtering not implemented yet")

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
        agents_by_host = load_all_agents_grouped_by_host(mngr_ctx)

        # Get all provider instances
        providers = get_all_provider_instances(mngr_ctx)
        provider_map = {provider.name: provider for provider in providers}
        logger.trace("Found {} hosts with agents", len(agents_by_host))

        # Process each host and its agents
        for host_ref, agent_refs in agents_by_host.items():
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

                host_info = HostInfo(
                    id=host.id,
                    name=host.connector.name,
                    provider_name=host_ref.provider_name,
                )

                # Get all agents on this host
                agents = host.get_agents()

                for agent_ref in agent_refs:
                    try:
                        # Find the agent in the list
                        agent = next((a for a in agents if a.id == agent_ref.agent_id), None)

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
                            idle_mode=None,
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


@deal.has()
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

    # Flatten host info for easier access
    if result.get("host"):
        host = result["host"]
        result["host_name"] = host.get("name", "")
        result["host_id"] = host.get("id", "")
        result["host_provider"] = host.get("provider_name", "")

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
