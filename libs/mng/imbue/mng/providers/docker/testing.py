from collections.abc import Generator
from pathlib import Path

import docker
import docker.errors

from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.docker.config import DockerProviderConfig
from imbue.mng.providers.docker.instance import DockerProviderInstance
from imbue.mng.providers.docker.volume import state_volume_name
from imbue.mng.providers.local.volume import LocalVolume
from imbue.mng.utils.testing import get_short_random_string


def make_docker_provider(mng_ctx: MngContext, name: str = "test-docker") -> DockerProviderInstance:
    config = DockerProviderConfig()
    return DockerProviderInstance(
        name=ProviderInstanceName(name),
        host_dir=Path("/mng"),
        mng_ctx=mng_ctx,
        config=config,
    )


def make_docker_provider_with_local_volume(
    mng_ctx: MngContext,
    volume_root: Path,
) -> DockerProviderInstance:
    """Create a Docker provider using a LocalVolume instead of a real Docker volume.

    This avoids needing a running Docker daemon for tests that only exercise
    state-volume logic (list_volumes, delete_volume, host store, etc.).
    """
    provider = make_docker_provider(mng_ctx)
    provider.__dict__["_state_volume"] = LocalVolume(root_path=volume_root)
    return provider


def make_docker_provider_with_cleanup(
    mng_ctx: MngContext,
) -> Generator[DockerProviderInstance, None, None]:
    """Create a Docker provider with a unique name and clean up all hosts on teardown."""
    unique_name = f"docker-test-{get_short_random_string()}"
    provider = make_docker_provider(mng_ctx, unique_name)
    yield provider

    try:
        cg = mng_ctx.concurrency_group
        discovered = provider.discover_hosts(cg, include_destroyed=True)
        for host in discovered:
            try:
                provider.destroy_host(host.host_id, delete_snapshots=True)
            except (MngError, docker.errors.DockerException, OSError):
                pass
    except (MngError, docker.errors.DockerException, OSError):
        pass

    try:
        for container in provider._list_containers():
            try:
                container.remove(force=True)
            except docker.errors.DockerException:
                pass
    except (MngError, docker.errors.DockerException):
        pass

    # Remove the Docker named volume backing the state container.
    try:
        user_id = str(mng_ctx.get_profile_user_id())
        prefix = mng_ctx.config.prefix
        vol_name = state_volume_name(prefix, user_id)
        provider._docker_client.volumes.get(vol_name).remove(force=True)
    except (docker.errors.NotFound, docker.errors.DockerException, OSError, MngError):
        pass

    try:
        provider.close()
    except (OSError, docker.errors.DockerException):
        pass
