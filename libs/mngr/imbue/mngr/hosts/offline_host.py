from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Callable

from loguru import logger
from pydantic import Field

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostState


class BaseHost(HostInterface):
    """Base for host implementations (shared between offline and online hosts)."""

    provider_instance: ProviderInstanceInterface = Field(
        frozen=True, description="The provider instance managing this host"
    )
    mngr_ctx: MngrContext = Field(frozen=True, repr=False, description="The mngr context")
    on_updated_host_data: Callable[[HostId, CertifiedHostData], None] | None = Field(
        frozen=True,
        default=None,
        description="Optional callback invoked when certified host data is updated",
    )

    @property
    def host_dir(self) -> Path:
        """Get the host state directory path from provider instance."""
        return self.provider_instance.host_dir

    # =========================================================================
    # Activity Configuration
    # =========================================================================

    def get_activity_config(self) -> ActivityConfig:
        """Get the activity configuration for this host."""
        certified_data = self.get_certified_data()
        return ActivityConfig(
            idle_mode=certified_data.idle_mode,
            idle_timeout_seconds=certified_data.idle_timeout_seconds,
            activity_sources=certified_data.activity_sources,
        )

    def set_activity_config(self, config: ActivityConfig) -> None:
        """Set the activity configuration for this host.

        Saves activity configuration to data.json, which is read by the
        activity_watcher.sh script using jq.
        """
        logger.debug(
            "Setting activity config for host {}: idle_mode={}, idle_timeout={}s",
            self.id,
            config.idle_mode,
            config.idle_timeout_seconds,
        )
        certified_data = self.get_certified_data()
        updated_data = certified_data.model_copy(
            update={
                "idle_mode": config.idle_mode,
                "idle_timeout_seconds": config.idle_timeout_seconds,
                "activity_sources": config.activity_sources,
            }
        )
        self.set_certified_data(updated_data)

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_plugin_data(self, plugin_name: str) -> dict[str, Any]:
        """Get certified plugin data from data.json."""
        certified_data = self.get_certified_data()
        return certified_data.plugin.get(plugin_name, {})

    # =========================================================================
    # Provider-Derived Information
    # =========================================================================

    def get_snapshots(self) -> list[SnapshotInfo]:
        """Get list of snapshots from the provider."""
        return self.provider_instance.list_snapshots(self)

    def get_image(self) -> str | None:
        """Get the image used for this host."""
        all_data = self.get_certified_data()
        return all_data.image

    def get_tags(self) -> dict[str, str]:
        """Get tags from the provider."""
        return self.provider_instance.get_host_tags(self)

    # =========================================================================
    # Agent Information
    # =========================================================================

    def _validate_and_create_agent_reference(self, agent_data: dict[str, Any]) -> AgentReference | None:
        """Validate agent data and create an AgentReference if valid.

        Returns None if the agent data is malformed (missing or invalid id/name).
        Logs warnings for malformed records.
        """
        agent_id_str = agent_data.get("id")
        if agent_id_str is None:
            logger.warning("Skipping malformed agent record for host {}: missing 'id': {}", self.id, agent_data)
            return None
        try:
            agent_id = AgentId(agent_id_str)
        except ValueError as e:
            logger.opt(exception=e).warning(
                "Skipping malformed agent record for host {}: invalid 'id': {}", self.id, agent_data
            )
            return None

        agent_name_str = agent_data.get("name")
        if agent_name_str is None:
            logger.warning("Skipping malformed agent record for host {}: missing 'name': {}", self.id, agent_data)
            return None
        try:
            agent_name = AgentName(agent_name_str)
        except ValueError as e:
            logger.opt(exception=e).warning(
                "Skipping malformed agent record for host {}: invalid 'name': {}", self.id, agent_data
            )
            return None

        return AgentReference(
            host_id=self.id,
            agent_id=agent_id,
            agent_name=agent_name,
            provider_name=self.provider_instance.name,
            certified_data=agent_data,
        )

    def get_agent_references(self) -> list[AgentReference]:
        """Return a list of all agent references for this host.

        For offline hosts, get agent information from the provider's persisted data.
        The full agent data.json contents are included as certified_data.
        Malformed agent records are skipped with a log.
        """
        agent_records = self.provider_instance.list_persisted_agent_data_for_host(self.id)

        agent_refs: list[AgentReference] = []
        for agent_data in agent_records:
            ref = self._validate_and_create_agent_reference(agent_data)
            if ref is not None:
                agent_refs.append(ref)

        return agent_refs

    # =========================================================================
    # Agent-Derived Information
    # =========================================================================
    def get_state(self) -> HostState:
        """Get the current state of the host.

        For offline hosts, we determine state based on certified data, stop_reason, and snapshots:
        - If certified data has state=FAILED, the host failed during creation
        - If snapshots exist:
          - stop_reason=PAUSED -> host became idle and was paused
          - stop_reason=STOPPED -> user explicitly stopped all agents on the host
          - stop_reason=None -> host crashed (no controlled shutdown recorded)
        - If no snapshots exist for a provider that supports them, the host is DESTROYED
        - If provider doesn't support snapshots, assume STOPPED
        """
        certified_data = self.get_certified_data()
        if certified_data.state == HostState.FAILED.value:
            return HostState.FAILED

        if self.provider_instance.supports_snapshots:
            try:
                snapshots = self.get_snapshots()
                if not snapshots:
                    return HostState.DESTROYED
            except (OSError, IOError, ConnectionError):
                # If we can't check snapshots, use stop_reason to determine state
                pass

        # Determine state based on stop_reason
        stop_reason = certified_data.stop_reason
        if stop_reason is None:
            return HostState.CRASHED
        else:
            return HostState(stop_reason)

    def get_failure_reason(self) -> str | None:
        """Get the failure reason if this host failed during creation."""
        return self.get_certified_data().failure_reason

    def get_build_log(self) -> str | None:
        """Get the build log if this host failed during creation."""
        return self.get_certified_data().build_log

    def get_permissions(self) -> list[str]:
        """Get the union of all agent permissions on this host.

        Uses persisted agent data from the provider to get permissions without
        requiring the host to be online.
        """
        permissions: set[str] = set()
        for agent_ref in self.get_agent_references():
            permissions.update(str(p) for p in agent_ref.permissions)
        return list(permissions)


class OfflineHost(BaseHost):
    """Host implementation that uses json data to enable reading the state of a host that is now offline.

    This is used when we have stored data about a host (e.g., from provider metadata or persisted
    agent data) but cannot currently connect to it. It provides read-only access to the host's
    last-known state.
    """

    certified_host_data: CertifiedHostData = Field(
        frozen=True,
        description="The certified host data loaded from data.json",
    )

    @property
    def is_local(self) -> bool:
        """Check if this host is local. Offline hosts are never local."""
        return False

    def get_name(self) -> HostName:
        """Return the human-readable name of this host from persisted data."""
        return HostName(self.certified_host_data.host_name)

    def get_stop_time(self) -> datetime | None:
        """Return the host last stop time as a datetime, or None if unknown."""
        return None

    def get_seconds_since_stopped(self) -> float | None:
        """Return the number of seconds since this host was stopped (or None if it is running)."""
        return None

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_certified_data(self) -> CertifiedHostData:
        return self.certified_host_data

    def set_certified_data(self, data: CertifiedHostData) -> None:
        """Save certified data to data.json and notify the provider."""
        assert self.on_updated_host_data is not None, "on_updated_host_data callback is not set"
        self.on_updated_host_data(self.id, data)
