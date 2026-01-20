from typing import Mapping
from typing import Sequence

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
    ) -> Host:
        raise NotImplementedError()

    def list_hosts(
        self,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        raise NotImplementedError()

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> Host:
        raise NotImplementedError()
