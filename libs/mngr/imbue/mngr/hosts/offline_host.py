from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

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
from imbue.mngr.primitives import HostState


class BaseHost(HostInterface):
    """Base for host implementations (shared between offline and online hosts)."""

    is_online: bool = Field(description="Whether the host is currently online/started")
    provider_instance: ProviderInstanceInterface = Field(
        frozen=True, description="The provider instance managing this host"
    )
    mngr_ctx: MngrContext = Field(frozen=True, repr=False, description="The mngr context")

    @property
    def host_dir(self) -> Path:
        """Get the host state directory path from provider instance."""
        return self.provider_instance.host_dir

    # =========================================================================
    # Activity Configuration
    # =========================================================================

    def get_activity_config(self) -> ActivityConfig:
        """Get the activity configuration for this host."""
        certified_data = self.get_all_certified_data()
        return ActivityConfig(
            idle_mode=certified_data.idle_mode,
            idle_timeout_seconds=certified_data.idle_timeout_seconds,
            activity_sources=certified_data.activity_sources,
        )

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_plugin_data(self, plugin_name: str) -> dict[str, Any]:
        """Get certified plugin data from data.json."""
        certified_data = self.get_all_certified_data()
        return certified_data.plugin.get(plugin_name, {})

    # =========================================================================
    # Provider-Derived Information
    # =========================================================================

    def get_snapshots(self) -> list[SnapshotInfo]:
        """Get list of snapshots from the provider."""
        return self.provider_instance.list_snapshots(self)

    def get_image(self) -> str | None:
        """Get the image used for this host."""
        all_data = self.get_all_certified_data()
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
            logger.warning(f"Skipping malformed agent record for host {self.id}: missing 'id': {agent_data}")
            return None
        try:
            agent_id = AgentId(agent_id_str)
        except ValueError as e:
            logger.opt(exception=e).warning(
                f"Skipping malformed agent record for host {self.id}: invalid 'id': {agent_data}"
            )
            return None

        agent_name_str = agent_data.get("name")
        if agent_name_str is None:
            logger.warning(f"Skipping malformed agent record for host {self.id}: missing 'name': {agent_data}")
            return None
        try:
            agent_name = AgentName(agent_name_str)
        except ValueError as e:
            logger.opt(exception=e).warning(
                f"Skipping malformed agent record for host {self.id}: invalid 'name': {agent_data}"
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

        For offline hosts, we determine state based on snapshots:
        - If snapshots exist, the host is STOPPED (can be restarted)
        - If no snapshots exist for a provider that supports them, the host is DESTROYED
        - If provider doesn't support snapshots, assume STOPPED
        """
        if self.provider_instance.supports_snapshots:
            try:
                snapshots = self.get_snapshots()
                if not snapshots:
                    return HostState.DESTROYED
            except (OSError, IOError, ConnectionError):
                # If we can't check snapshots, assume STOPPED (safer default)
                pass

        return HostState.STOPPED

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
    is_online: bool = Field(default=False, description="Whether the host is currently online/started")

    @property
    def is_local(self) -> bool:
        """Check if this host is local. Offline hosts are never local."""
        return False

    # TODO: add another field like certified_host_data (certified_host_data_mtime) to track when data.json was last updated
    #  then use that here and in get_seconds_since_stopped
    def get_stop_time(self) -> datetime | None:
        """Return the host last stop time as a datetime, or None if unknown."""
        return None

    def get_seconds_since_stopped(self) -> float | None:
        """Return the number of seconds since this host was stopped (or None if it is running)."""
        return None

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_all_certified_data(self) -> CertifiedHostData:
        return self.certified_host_data
