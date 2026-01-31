from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ActivitySource
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

    def get_agent_references(self) -> list[AgentReference]:
        """Return a list of all agent references for this host.

        For offline hosts, get agent information from the provider's persisted data.
        """
        agent_refs: list[AgentReference] = []
        try:
            agent_records = self.provider_instance.list_persisted_agent_data_for_host(self.id)
            for agent_data in agent_records:
                agent_refs.append(
                    AgentReference(
                        host_id=self.id,
                        agent_id=AgentId(agent_data["id"]),
                        agent_name=AgentName(agent_data["name"]),
                        provider_name=self.provider_instance.name,
                    )
                )
        except (KeyError, ValueError):
            pass

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

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_all_certified_data(self) -> CertifiedHostData:
        return self.certified_host_data

    # =========================================================================
    # Activity Times
    # =========================================================================

    def get_reported_activity_time(self, activity_type: ActivitySource) -> datetime | None:
        """Get the last reported activity time for the given type.

        For offline hosts, we cannot retrieve activity times since we can't read the
        activity files from the host filesystem. Returns None.
        """
        return None

    # =========================================================================
    # Agent-Derived Information
    # =========================================================================

    def get_idle_seconds(self) -> float:
        """Get the number of seconds since last activity.

        For offline hosts, return infinity since we can't track activity.
        """
        return float("inf")

    def get_permissions(self) -> list[str]:
        """Get the union of all agent permissions on this host.

        For offline hosts, we cannot retrieve permissions since we can't read
        agent data files from the host filesystem. Returns an empty list.
        """
        return []
