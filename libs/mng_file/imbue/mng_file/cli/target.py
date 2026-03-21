from pathlib import Path
from typing import assert_never

from loguru import logger
from pydantic import ConfigDict
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mng.api.discover import discover_all_hosts_and_agents
from imbue.mng.api.find import resolve_agent_reference
from imbue.mng.api.find import resolve_host_reference
from imbue.mng.api.providers import get_provider_instance
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng.errors import UserInputError
from imbue.mng.hosts.host import get_agent_state_dir_path
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.interfaces.volume import Volume
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import DiscoveredAgent
from imbue.mng.primitives import DiscoveredHost
from imbue.mng.primitives import HostId
from imbue.mng.providers.base_provider import BaseProviderInstance
from imbue.mng_file.data_types import PathRelativeTo


@pure
def resolve_full_path(base_path: Path, user_path: str) -> Path:
    """Combine a base path with a user-provided path, respecting absolute paths."""
    parsed = Path(user_path)
    if parsed.is_absolute():
        return parsed
    return base_path / parsed


@pure
def _compute_agent_base_path(
    relative_to: PathRelativeTo,
    work_dir: Path,
    host_dir: Path,
    agent_id: AgentId,
) -> Path:
    match relative_to:
        case PathRelativeTo.WORK:
            return work_dir
        case PathRelativeTo.STATE:
            return get_agent_state_dir_path(host_dir, agent_id)
        case PathRelativeTo.HOST:
            return host_dir
        case _ as unreachable:
            assert_never(unreachable)


@pure
def _is_volume_accessible_path(relative_to: PathRelativeTo) -> bool:
    """Whether the given relative_to mode produces paths under host_dir (accessible via volume)."""
    match relative_to:
        case PathRelativeTo.WORK:
            return False
        case PathRelativeTo.STATE:
            return True
        case PathRelativeTo.HOST:
            return True
        case _ as unreachable:
            assert_never(unreachable)


@pure
def compute_volume_path(
    relative_to: PathRelativeTo,
    agent_id: AgentId | None,
    user_path: str | None,
) -> str:
    """Compute the path within a volume for a given relative_to mode and user path.

    Volume paths are relative to the host_dir root. Returns a path string
    suitable for Volume.read_file() and Volume.listdir().
    """
    match relative_to:
        case PathRelativeTo.HOST:
            if user_path is None:
                return "."
            return user_path
        case PathRelativeTo.STATE:
            if agent_id is None:
                raise UserInputError("--relative-to state requires an agent target")
            base = f"agents/{agent_id}"
            if user_path is None:
                return base
            return f"{base}/{user_path}"
        case PathRelativeTo.WORK:
            raise UserInputError(
                "Cannot access work directory files when the host is offline. "
                "Use --relative-to state or --relative-to host instead."
            )
        case _ as unreachable:
            assert_never(unreachable)


class ResolveFileTargetResult(FrozenModel):
    """Result of resolving a file command target to access methods and base path."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    online_host: OnlineHostInterface | None = Field(default=None, description="Online host for direct access")
    volume: Volume | None = Field(default=None, description="Volume for offline access")
    base_path: Path = Field(description="Base path for resolving relative paths")
    is_agent: bool = Field(description="Whether the target is an agent (vs a host)")
    agent_id: AgentId | None = Field(default=None, description="Agent ID if target is an agent")
    relative_to: PathRelativeTo = Field(description="Path resolution mode")

    @property
    def host(self) -> OnlineHostInterface:
        """Get the online host, raising if not available."""
        if self.online_host is None:
            raise MngError(
                "Host is offline and this operation requires direct host access. "
                "Use --relative-to state or --relative-to host for offline access."
            )
        return self.online_host

    @property
    def is_online(self) -> bool:
        return self.online_host is not None


def resolve_file_target(
    target_identifier: str,
    mng_ctx: MngContext,
    relative_to: PathRelativeTo,
) -> ResolveFileTargetResult:
    """Resolve a TARGET argument to a host/volume and base path for file operations.

    Tries agent resolution first, then host resolution. If both match, raises
    an error requiring disambiguation. If neither matches, raises an error.

    When the target host is online, direct host access is used. When offline,
    falls back to volume access for paths under the host directory.
    """
    with log_span("Discovering hosts and agents"):
        agents_by_host, _ = discover_all_hosts_and_agents(mng_ctx, include_destroyed=False)

    all_hosts = list(agents_by_host.keys())

    # Try agent resolution
    agent_result: tuple[DiscoveredHost, DiscoveredAgent] | None = None
    try:
        agent_result = resolve_agent_reference(
            agent_identifier=target_identifier,
            resolved_host=None,
            agents_by_host=agents_by_host,
        )
    except UserInputError as err:
        if "Multiple" in str(err):
            raise
        pass

    # Try host resolution
    host_result: DiscoveredHost | None = None
    try:
        host_result = resolve_host_reference(
            host_identifier=target_identifier,
            all_hosts=all_hosts,
        )
    except UserInputError as err:
        if "Multiple" in str(err):
            raise
        pass

    # Check for ambiguity
    if agent_result is not None and host_result is not None:
        raise UserInputError(
            f"'{target_identifier}' matches both an agent and a host. "
            f"Use the full ID to disambiguate.\n\n"
            f"To see all IDs, run:\n"
            f"  mng list --fields id,name,host"
        )

    # Neither matched
    if agent_result is None and host_result is None:
        raise UserInputError(
            f"No agent or host found matching: {target_identifier}\n\nTo see available agents, run:\n  mng list"
        )

    # Agent matched
    if agent_result is not None:
        discovered_host, discovered_agent = agent_result
        return _resolve_agent_target(
            discovered_host=discovered_host,
            discovered_agent=discovered_agent,
            mng_ctx=mng_ctx,
            relative_to=relative_to,
        )

    # Host matched
    assert host_result is not None
    if relative_to != PathRelativeTo.HOST and relative_to != PathRelativeTo.WORK:
        raise UserInputError(
            f"--relative-to {relative_to.value.lower()} is only valid for agent targets. "
            f"Host targets always use MNG_HOST_DIR as the base path."
        )
    return _resolve_host_target(
        discovered_host=host_result,
        mng_ctx=mng_ctx,
    )


def _try_get_online_host(
    provider: "BaseProviderInstance",
    host_id: "HostId",
) -> OnlineHostInterface | None:
    """Try to get an online host interface, returning None if the host is offline."""
    try:
        host_interface = provider.get_host(host_id)
    except MngError as err:
        logger.trace("Host {} is not available: {}", host_id, err)
        return None

    if not isinstance(host_interface, OnlineHostInterface):
        return None

    return host_interface


def _resolve_agent_target(
    discovered_host: DiscoveredHost,
    discovered_agent: DiscoveredAgent,
    mng_ctx: MngContext,
    relative_to: PathRelativeTo,
) -> ResolveFileTargetResult:
    with log_span("Getting access for agent target"):
        provider = get_provider_instance(discovered_host.provider_name, mng_ctx)

    # Try online access
    online_host = _try_get_online_host(provider, discovered_host.host_id)

    # Try volume access
    host_volume = provider.get_volume_for_host(discovered_host.host_id)
    volume: Volume | None = None
    if host_volume is not None:
        volume = host_volume.volume

    if online_host is None and volume is None:
        raise MngError(
            f"Host for agent '{discovered_agent.agent_name}' is offline and the provider "
            f"does not support volume access. Cannot access files."
        )

    # When online, get work_dir from the host's agent list
    work_dir: Path | None = None
    host_dir: Path | None = None
    if online_host is not None:
        host_dir = online_host.host_dir
        for agent_ref in online_host.discover_agents():
            if agent_ref.agent_id == discovered_agent.agent_id:
                work_dir = agent_ref.work_dir
                break

    # When offline, use discovered data for work_dir
    if work_dir is None:
        work_dir = discovered_agent.work_dir

    if work_dir is None and relative_to == PathRelativeTo.WORK:
        raise UserInputError(f"Could not determine work directory for agent: {discovered_agent.agent_name}")

    # For offline + work_dir relative, we can't use volume
    if online_host is None and not _is_volume_accessible_path(relative_to):
        raise UserInputError(
            "Host is offline. Work directory files are not accessible via volume. "
            "Use --relative-to state or --relative-to host for offline access."
        )

    # Compute a synthetic host_dir for path computation when offline
    if host_dir is None:
        # Volume is rooted at host_dir, so we use a placeholder
        host_dir = Path("/mng-host-dir")

    base_path = _compute_agent_base_path(
        relative_to=relative_to,
        work_dir=work_dir if work_dir is not None else Path("/unknown"),
        host_dir=host_dir,
        agent_id=discovered_agent.agent_id,
    )
    logger.debug("Resolved agent target: base_path={}, is_online={}", base_path, online_host is not None)

    return ResolveFileTargetResult(
        online_host=online_host,
        volume=volume,
        base_path=base_path,
        is_agent=True,
        agent_id=discovered_agent.agent_id,
        relative_to=relative_to,
    )


def _resolve_host_target(
    discovered_host: DiscoveredHost,
    mng_ctx: MngContext,
) -> ResolveFileTargetResult:
    with log_span("Getting access for host target"):
        provider = get_provider_instance(discovered_host.provider_name, mng_ctx)

    # Try online access
    online_host = _try_get_online_host(provider, discovered_host.host_id)

    # Try volume access
    host_volume = provider.get_volume_for_host(discovered_host.host_id)
    volume: Volume | None = None
    if host_volume is not None:
        volume = host_volume.volume

    if online_host is None and volume is None:
        raise MngError(
            f"Host '{discovered_host.host_name}' is offline and the provider "
            f"does not support volume access. Cannot access files."
        )

    if online_host is not None:
        base_path = online_host.host_dir
    else:
        base_path = Path("/mng-host-dir")

    logger.debug("Resolved host target: base_path={}, is_online={}", base_path, online_host is not None)

    return ResolveFileTargetResult(
        online_host=online_host,
        volume=volume,
        base_path=base_path,
        is_agent=False,
        agent_id=None,
        relative_to=PathRelativeTo.HOST,
    )
