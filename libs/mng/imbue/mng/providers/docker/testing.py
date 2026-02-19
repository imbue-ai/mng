from collections.abc import Generator
from pathlib import Path

import docker.errors

from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.docker.config import DockerProviderConfig
from imbue.mng.providers.docker.instance import DockerProviderInstance
from imbue.mng.utils.testing import get_short_random_string


def make_docker_provider(mng_ctx: MngContext, name: str = "test-docker") -> DockerProviderInstance:
    config = DockerProviderConfig()
    return DockerProviderInstance(
        name=ProviderInstanceName(name),
        host_dir=Path("/mng"),
        mng_ctx=mng_ctx,
        config=config,
    )


def make_docker_provider_with_cleanup(
    mng_ctx: MngContext,
) -> Generator[DockerProviderInstance, None, None]:
    """Create a Docker provider with a unique name and clean up all hosts on teardown."""
    unique_name = f"docker-test-{get_short_random_string()}"
    provider = make_docker_provider(mng_ctx, unique_name)
    yield provider

    try:
        cg = mng_ctx.concurrency_group
        hosts = provider.list_hosts(cg, include_destroyed=True)
        for host in hosts:
            try:
                provider.destroy_host(host, delete_snapshots=True)
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

    try:
        provider.close()
    except (OSError, docker.errors.DockerException):
        pass
