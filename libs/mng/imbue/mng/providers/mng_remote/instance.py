from collections.abc import Mapping
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from typing import Any

from loguru import logger
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import SecretStr
from pyinfra.api.host import Host as PyinfraHost

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.api.data_types import HostLifecycleOptions
from imbue.mng.errors import HostNotFoundError
from imbue.mng.errors import ProviderError
from imbue.mng.hosts.host import Host
from imbue.mng.interfaces.data_types import CertifiedHostData
from imbue.mng.interfaces.data_types import HostResources
from imbue.mng.interfaces.data_types import SnapshotInfo
from imbue.mng.interfaces.data_types import VolumeInfo
from imbue.mng.interfaces.host import HostInterface
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostName
from imbue.mng.primitives import HostState
from imbue.mng.primitives import ImageReference
from imbue.mng.primitives import SnapshotId
from imbue.mng.primitives import SnapshotName
from imbue.mng.primitives import VolumeId
from imbue.mng.providers.base_provider import BaseProviderInstance
from imbue.mng.providers.mng_remote.client import MngRemoteClient
from imbue.mng.providers.mng_remote.remote_host import RemoteHost


class MngRemoteProviderInstance(BaseProviderInstance):
    """Provider instance that proxies operations to a remote mng API server.

    This allows `mng list` on one machine to show agents managed by
    a remote mng instance, without needing SSH keys or cloud credentials.

    Currently supports read-only operations (listing agents). Write operations
    should be performed through the remote mng CLI or web UI.
    """

    remote_url: str = Field(frozen=True, description="Base URL of the remote mng API server")
    remote_token: SecretStr = Field(frozen=True, description="Bearer token for the remote API server")

    _host_cache: dict[HostId, RemoteHost] = PrivateAttr(default_factory=dict)

    def _get_client(self) -> MngRemoteClient:
        """Create a client for the remote API server."""
        return MngRemoteClient(base_url=self.remote_url, token=self.remote_token)

    @property
    def is_authorized(self) -> bool:
        return True

    @property
    def supports_snapshots(self) -> bool:
        return False

    @property
    def supports_shutdown_hosts(self) -> bool:
        return False

    @property
    def supports_volumes(self) -> bool:
        return False

    @property
    def supports_mutable_tags(self) -> bool:
        return False

    def list_hosts(
        self,
        cg: ConcurrencyGroup,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List hosts from the remote API server.

        Fetches agents from the remote API, groups them by host, and creates
        RemoteHost objects for each unique host found. Raises ProviderError
        if the remote server is unreachable (propagated through the listing
        pipeline as a ProviderErrorInfo).
        """
        all_agents = self._get_client().list_agents()

        # Group agents by host ID
        agents_by_host: dict[str, list[dict[str, Any]]] = {}
        host_data_by_id: dict[str, dict[str, Any]] = {}
        for agent in all_agents:
            host_info = agent.get("host", {})
            host_id_str = host_info.get("id")
            if host_id_str is None:
                logger.warning("Skipping agent without host ID from remote API: {}", agent.get("id"))
                continue
            agents_by_host.setdefault(host_id_str, []).append(agent)
            if host_id_str not in host_data_by_id:
                host_data_by_id[host_id_str] = host_info

        # Create RemoteHost objects for each unique host
        self._host_cache.clear()
        hosts: list[HostInterface] = []
        now = datetime.now(timezone.utc)
        for host_id_str, host_info in host_data_by_id.items():
            host_id = HostId(host_id_str)

            state_str = host_info.get("state")
            remote_state = HostState(state_str) if state_str else HostState.RUNNING

            certified_data = CertifiedHostData(
                host_id=host_id_str,
                host_name=host_info.get("name", host_id_str),
                created_at=now,
                updated_at=now,
                user_tags=host_info.get("tags", {}),
                image=host_info.get("image"),
                # stop_reason is not used by RemoteHost.get_state() but set for consistency
                stop_reason=state_str,
            )

            remote_host = RemoteHost(
                id=host_id,
                provider_instance=self,
                mng_ctx=self.mng_ctx,
                certified_host_data=certified_data,
                remote_state=remote_state,
                remote_agent_data=tuple(agents_by_host[host_id_str]),
            )
            hosts.append(remote_host)
            self._host_cache[host_id] = remote_host

        return hosts

    def list_persisted_agent_data_for_host(self, host_id: HostId) -> list[dict]:
        """Fetch agent data from the remote API server.

        Returns cached data if available from a prior list_hosts() call,
        otherwise fetches fresh from the API. Raises ProviderError if
        the remote server is unreachable.
        """
        cached_host = self._host_cache.get(host_id)
        if cached_host is not None:
            return list(cached_host.remote_agent_data)

        all_agents = self._get_client().list_agents()
        return [a for a in all_agents if a.get("host", {}).get("id") == str(host_id)]

    def get_host(self, host: HostId | HostName) -> HostInterface:
        """Return a cached host from the most recent list_hosts() call."""
        if isinstance(host, HostId):
            cached = self._host_cache.get(host)
            if cached is not None:
                return cached
        else:
            for cached_host in self._host_cache.values():
                if cached_host.get_name() == host:
                    return cached_host
        raise HostNotFoundError(host)

    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
        lifecycle: HostLifecycleOptions | None = None,
        known_hosts: Sequence[str] | None = None,
        authorized_keys: Sequence[str] | None = None,
        snapshot: SnapshotName | None = None,
    ) -> Host:
        raise ProviderError("Cannot create hosts through mng remote provider. Use the remote mng instance directly.")

    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        raise ProviderError("Cannot stop hosts through mng remote provider. Use the remote mng instance directly.")

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        raise ProviderError("Cannot start hosts through mng remote provider. Use the remote mng instance directly.")

    def destroy_host(
        self,
        host: HostInterface | HostId,
    ) -> None:
        raise ProviderError(
            "Cannot destroy hosts through mng remote provider. Use the remote mng instance directly."
        )

    def delete_host(self, host: HostInterface) -> None:
        raise ProviderError(
            "Cannot delete hosts through mng remote provider. Use the remote mng instance directly."
        )

    def on_connection_error(self, host_id: HostId) -> None:
        logger.debug("Connection error for remote host {}", host_id)

    def get_host_resources(self, host: HostInterface) -> HostResources:
        raise ProviderError("Cannot query host resources through mng remote provider.")

    def create_snapshot(self, host: HostInterface | HostId, name: SnapshotName | None = None) -> SnapshotId:
        raise ProviderError("Snapshots not supported through mng remote provider.")

    def list_snapshots(self, host: HostInterface | HostId) -> list[SnapshotInfo]:
        return []

    def delete_snapshot(self, host: HostInterface | HostId, snapshot_id: SnapshotId) -> None:
        raise ProviderError("Snapshots not supported through mng remote provider.")

    def list_volumes(self) -> list[VolumeInfo]:
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        raise ProviderError("Volumes not supported through mng remote provider.")

    def get_host_tags(self, host: HostInterface | HostId) -> dict[str, str]:
        return {}

    def set_host_tags(self, host: HostInterface | HostId, tags: Mapping[str, str]) -> None:
        raise ProviderError("Cannot set tags through mng remote provider.")

    def add_tags_to_host(self, host: HostInterface | HostId, tags: Mapping[str, str]) -> None:
        raise ProviderError("Cannot set tags through mng remote provider.")

    def remove_tags_from_host(self, host: HostInterface | HostId, keys: Sequence[str]) -> None:
        raise ProviderError("Cannot remove tags through mng remote provider.")

    def get_connector(self, host: HostInterface | HostId) -> PyinfraHost:
        raise ProviderError("Cannot get connectors through mng remote provider.")
