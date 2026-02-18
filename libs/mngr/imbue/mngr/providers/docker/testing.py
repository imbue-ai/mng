from collections.abc import Generator
from pathlib import Path

import docker.errors

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.docker.config import DockerProviderConfig
from imbue.mngr.providers.docker.instance import DockerProviderInstance
from imbue.mngr.utils.testing import get_short_random_string


def make_docker_provider(mngr_ctx: MngrContext, name: str = "test-docker") -> DockerProviderInstance:
    config = DockerProviderConfig()
    return DockerProviderInstance(
        name=ProviderInstanceName(name),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        config=config,
    )


def make_docker_provider_with_cleanup(
    mngr_ctx: MngrContext,
) -> Generator[DockerProviderInstance, None, None]:
    """Create a Docker provider with a unique name and clean up all hosts on teardown."""
    unique_name = f"docker-test-{get_short_random_string()}"
    provider = make_docker_provider(mngr_ctx, unique_name)
    yield provider

    try:
        cg = mngr_ctx.concurrency_group
        hosts = provider.list_hosts(cg, include_destroyed=True)
        for host in hosts:
            try:
                provider.destroy_host(host, delete_snapshots=True)
            except (MngrError, docker.errors.DockerException, OSError):
                pass
    except (MngrError, docker.errors.DockerException, OSError):
        pass

    try:
        for container in provider._list_containers():
            try:
                container.remove(force=True)
            except docker.errors.DockerException:
                pass
    except (MngrError, docker.errors.DockerException):
        pass

    try:
        provider.close()
    except (OSError, docker.errors.DockerException):
        pass
