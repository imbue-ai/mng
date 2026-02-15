from typing import Mapping
from typing import Sequence

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import SnapshotId


class BaseProviderInstance(ProviderInstanceInterface):
    """
    Abstract base class for provider instances.

    Useful because it communicates that the concrete Host class (not HostInterface) is returned from these methods.
    """

    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
        lifecycle: HostLifecycleOptions | None = None,
        known_hosts: Sequence[str] | None = None,
    ) -> Host:
        raise NotImplementedError()

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        raise NotImplementedError()

    def get_host(
        self,
        host: HostId | HostName,
    ) -> HostInterface:
        raise NotImplementedError()

    def list_hosts(
        self,
        cg: ConcurrencyGroup,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        raise NotImplementedError()

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> HostInterface:
        raise NotImplementedError()

    # FIXME: make this configurable at the provider level, eg, give them all settings for this
    def get_max_destroyed_host_persisted_seconds(self) -> float:
        # currently default: 7 days, can be overridden by providers that persist destroyed hosts longer
        return 60.0 * 60.0 * 24.0 * 7.0
