from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.common import LOCAL_CONNECTOR_NAME
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostState


class OfflineHost(HostInterface):
    """Host implementation that uses json data to enable reading the state of a host that is now offline.

    All operations (command execution, file read/write) are performed through
    the pyinfra connector, which handles both local and remote hosts transparently.
    """

    certified_host_data: CertifiedHostData = Field(
        frozen=True, description="The certified host data loaded from data.json"
    )
    is_online: bool = Field(default=False, description="Whether the host is currently online/started")
    provider_instance: ProviderInstanceInterface = Field(
        frozen=True, description="The provider instance managing this host"
    )
    mngr_ctx: MngrContext = Field(frozen=True, repr=False, description="The mngr context")

    @property
    def is_local(self) -> bool:
        """Check if this host uses the local connector."""
        return self.connector.connector_cls_name == LOCAL_CONNECTOR_NAME

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
    # Activity Times
    # =========================================================================

    # TODO: simply report the time that this host was stopped/destroyed
    def get_reported_activity_time(self, activity_type: ActivitySource) -> datetime | None:
        """Get the last reported activity time for the given type."""
        ...

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_all_certified_data(self) -> CertifiedHostData:
        return self.certified_host_data

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

    # TODO: implement. See how we get this in load_all_agents_grouped_by_host when the host is offlien, that should be here instead
    def get_agent_references(self) -> list[AgentReference]:
        """Return a list of all agent references for this host."""
        ...

    # =========================================================================
    # Agent-Derived Information
    # =========================================================================

    # NOTE: Ignore this one for now!
    def get_permissions(self) -> list[str]:
        """Get the union of all agent permissions on this host."""
        raise NotImplementedError("Not implemented for offline hosts yet, will come back to this later")

    # TODO: implement. take a look at the implementation in Host--some of it can be split up to here (the bit about distinguishing between stopped and destroyed)
    def get_state(self) -> HostState:
        """Get the current state of the host."""
        ...
