from collections.abc import Sequence

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.utils.error_handling import handle_error_with_behavior


class EnforceAction(FrozenModel):
    """A single enforcement action taken or proposed."""

    host_id: HostId = Field(description="The host that was acted upon")
    host_name: str = Field(description="Human-readable host name")
    provider_name: ProviderInstanceName = Field(description="Provider instance name")
    host_state: HostState = Field(description="Host state at the time of the action")
    action: str = Field(description="Action taken: stop_host or destroy_host")
    reason: str = Field(description="Human-readable reason for the action")
    is_dry_run: bool = Field(description="Whether this was a dry-run action")


class EnforceResult(MutableModel):
    """Aggregated results of enforcement checks."""

    actions: list[EnforceAction] = Field(
        default_factory=list,
        description="Enforcement actions taken or proposed",
    )
    hosts_checked: int = Field(default=0, description="Total hosts checked")
    idle_violations: int = Field(default=0, description="Hosts exceeding idle timeout")
    timeout_violations: int = Field(default=0, description="Hosts stuck in transitory states")
    errors: list[str] = Field(default_factory=list, description="Errors encountered")


def enforce(
    providers: Sequence[ProviderInstanceInterface],
    is_check_idle: bool,
    is_check_timeouts: bool,
    building_timeout_seconds: int,
    starting_timeout_seconds: int,
    stopping_timeout_seconds: int,
    is_dry_run: bool,
    error_behavior: ErrorBehavior,
) -> EnforceResult:
    """Enforce host idle timeouts and detect stuck state transitions.

    Iterates over all hosts from the provided providers, checking for idle
    violations and transitory state timeouts. Takes corrective action (stop
    or destroy) unless in dry-run mode.
    """
    result = EnforceResult()
    logger.trace(
        "Configured enforce: is_check_idle={} is_check_timeouts={} is_dry_run={}",
        is_check_idle,
        is_check_timeouts,
        is_dry_run,
    )

    for provider in providers:
        try:
            hosts = provider.list_hosts(include_destroyed=False)
        except MngrError as e:
            error_msg = f"Failed to list hosts for provider {provider.name}: {e}"
            result.errors.append(error_msg)
            handle_error_with_behavior(error_msg, error_behavior, exc=e)
            continue

        for host in hosts:
            result.hosts_checked = result.hosts_checked + 1

            try:
                _enforce_host(
                    host=host,
                    provider=provider,
                    is_check_idle=is_check_idle,
                    is_check_timeouts=is_check_timeouts,
                    building_timeout_seconds=building_timeout_seconds,
                    starting_timeout_seconds=starting_timeout_seconds,
                    stopping_timeout_seconds=stopping_timeout_seconds,
                    is_dry_run=is_dry_run,
                    result=result,
                )
            except MngrError as e:
                error_msg = f"Failed to enforce host {host.id}: {e}"
                result.errors.append(error_msg)
                handle_error_with_behavior(error_msg, error_behavior, exc=e)

    return result


def _enforce_host(
    host: HostInterface,
    provider: ProviderInstanceInterface,
    is_check_idle: bool,
    is_check_timeouts: bool,
    building_timeout_seconds: int,
    starting_timeout_seconds: int,
    stopping_timeout_seconds: int,
    is_dry_run: bool,
    result: EnforceResult,
) -> None:
    """Check a single host and take enforcement action if needed."""
    state = host.get_state()
    host_name = str(host.get_name())

    match state:
        case HostState.RUNNING:
            if is_check_idle:
                _check_idle_host(
                    host=host,
                    host_name=host_name,
                    provider=provider,
                    is_dry_run=is_dry_run,
                    result=result,
                )

        case HostState.BUILDING:
            if is_check_timeouts:
                # Building hosts are not yet online, so we cannot query uptime.
                # We lack a reliable creation timestamp at this layer, so log
                # and skip for now.
                logger.debug(
                    "Skipped timeout check for BUILDING host {} (no creation timestamp available)",
                    host.id,
                )

        case HostState.STARTING:
            if is_check_timeouts:
                _check_starting_host(
                    host=host,
                    host_name=host_name,
                    provider=provider,
                    starting_timeout_seconds=starting_timeout_seconds,
                    is_dry_run=is_dry_run,
                    result=result,
                )

        case HostState.STOPPING:
            if is_check_timeouts:
                _check_stopping_host(
                    host=host,
                    host_name=host_name,
                    provider=provider,
                    stopping_timeout_seconds=stopping_timeout_seconds,
                    is_dry_run=is_dry_run,
                    result=result,
                )

        case HostState.STOPPED | HostState.PAUSED | HostState.CRASHED | HostState.FAILED | HostState.DESTROYED:
            # Nothing to enforce on these states
            logger.trace("Skipped host {} in state {}", host.id, state)


def _check_idle_host(
    host: HostInterface,
    host_name: str,
    provider: ProviderInstanceInterface,
    is_dry_run: bool,
    result: EnforceResult,
) -> None:
    """Check if a running host has exceeded its idle timeout."""
    if not isinstance(host, OnlineHostInterface):
        logger.trace("Skipped idle check for host {} (not online)", host.id)
        return

    # Skip local hosts -- they cannot be stopped via provider
    if host.is_local:
        logger.trace("Skipped idle check for local host {}", host.id)
        return

    try:
        idle_seconds = host.get_idle_seconds()
    except HostOfflineError:
        logger.trace("Skipped idle check for host {} (went offline)", host.id)
        return

    activity_config = host.get_activity_config()
    idle_timeout_seconds = activity_config.idle_timeout_seconds

    if idle_seconds <= idle_timeout_seconds:
        logger.trace(
            "Host {} is within idle timeout ({:.0f}s / {}s)",
            host.id,
            idle_seconds,
            idle_timeout_seconds,
        )
        return

    reason = f"Host idle for {idle_seconds:.0f}s, exceeding timeout of {idle_timeout_seconds}s"

    with log_span("Stopping idle host {}", host.id):
        if not is_dry_run:
            provider.stop_host(host)

    action = EnforceAction(
        host_id=host.id,
        host_name=host_name,
        provider_name=provider.name,
        host_state=HostState.RUNNING,
        action="stop_host",
        reason=reason,
        is_dry_run=is_dry_run,
    )
    result.actions.append(action)
    result.idle_violations = result.idle_violations + 1


def _check_starting_host(
    host: HostInterface,
    host_name: str,
    provider: ProviderInstanceInterface,
    starting_timeout_seconds: int,
    is_dry_run: bool,
    result: EnforceResult,
) -> None:
    """Check if a host has been stuck in STARTING state too long."""
    if not isinstance(host, OnlineHostInterface):
        logger.trace("Skipped starting timeout check for host {} (not online)", host.id)
        return

    try:
        uptime_seconds = host.get_uptime_seconds()
    except HostOfflineError:
        logger.trace("Skipped starting timeout check for host {} (went offline)", host.id)
        return

    if uptime_seconds <= starting_timeout_seconds:
        logger.trace(
            "Host {} STARTING within timeout ({:.0f}s / {}s)",
            host.id,
            uptime_seconds,
            starting_timeout_seconds,
        )
        return

    reason = f"Host stuck in STARTING for {uptime_seconds:.0f}s, exceeding timeout of {starting_timeout_seconds}s"

    with log_span("Stopping stuck STARTING host {}", host.id):
        if not is_dry_run:
            provider.stop_host(host)

    action = EnforceAction(
        host_id=host.id,
        host_name=host_name,
        provider_name=provider.name,
        host_state=HostState.STARTING,
        action="stop_host",
        reason=reason,
        is_dry_run=is_dry_run,
    )
    result.actions.append(action)
    result.timeout_violations = result.timeout_violations + 1


def _check_stopping_host(
    host: HostInterface,
    host_name: str,
    provider: ProviderInstanceInterface,
    stopping_timeout_seconds: int,
    is_dry_run: bool,
    result: EnforceResult,
) -> None:
    """Check if a host has been stuck in STOPPING state too long."""
    # For stopping hosts, we try to check how long they've been stopping.
    # If the host is still online, we can use uptime as a proxy.
    if not isinstance(host, OnlineHostInterface):
        logger.trace("Skipped stopping timeout check for host {} (not online)", host.id)
        return

    try:
        uptime_seconds = host.get_uptime_seconds()
    except HostOfflineError:
        logger.trace("Skipped stopping timeout check for host {} (went offline)", host.id)
        return

    if uptime_seconds <= stopping_timeout_seconds:
        logger.trace(
            "Host {} STOPPING within timeout ({:.0f}s / {}s)",
            host.id,
            uptime_seconds,
            stopping_timeout_seconds,
        )
        return

    reason = f"Host stuck in STOPPING for {uptime_seconds:.0f}s, exceeding timeout of {stopping_timeout_seconds}s"

    # Destroy instead of stop since the host is already failing to stop
    with log_span("Destroying stuck STOPPING host {}", host.id):
        if not is_dry_run:
            provider.destroy_host(host)

    action = EnforceAction(
        host_id=host.id,
        host_name=host_name,
        provider_name=provider.name,
        host_state=HostState.STOPPING,
        action="destroy_host",
        reason=reason,
        is_dry_run=is_dry_run,
    )
    result.actions.append(action)
    result.timeout_violations = result.timeout_violations + 1
