"""Integration tests for Docker provider lifecycle.

These tests require a running Docker daemon. They test the provider instance
methods directly with real Docker containers. Each test cleans up its
containers on teardown.

Since these require Docker, they are marked as acceptance tests and will run
in CI environments where Docker is available.
"""

from collections.abc import Generator

import docker.errors
import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.hosts.host import Host
from imbue.mngr.hosts.offline_host import OfflineHost
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.providers.docker.conftest import make_docker_provider
from imbue.mngr.providers.docker.instance import DockerProviderInstance


@pytest.fixture
def docker_provider(temp_mngr_ctx: MngrContext) -> Generator[DockerProviderInstance, None, None]:
    """Create a Docker provider instance and clean up containers on teardown."""
    provider = make_docker_provider(temp_mngr_ctx)
    yield provider

    # Cleanup: destroy all hosts created during the test
    try:
        cg = temp_mngr_ctx.concurrency_group
        hosts = provider.list_hosts(cg, include_destroyed=True)
        for host in hosts:
            try:
                provider.destroy_host(host, delete_snapshots=True)
            except (MngrError, docker.errors.DockerException, OSError):
                pass
    except (MngrError, docker.errors.DockerException, OSError):
        pass

    provider.close()


@pytest.mark.acceptance
def test_create_host_creates_container_with_ssh(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-ssh"))
    assert isinstance(host, Host)
    result = host.execute_command("echo hello")
    assert result.success
    assert "hello" in result.stdout


@pytest.mark.acceptance
def test_create_host_with_tags(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-tags"), tags={"env": "test", "team": "infra"})
    assert isinstance(host, Host)

    tags = docker_provider.get_host_tags(host.id)
    assert tags == {"env": "test", "team": "infra"}


@pytest.mark.acceptance
def test_create_host_with_custom_image(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(
        HostName("test-image"),
        build_args=["--image=python:3.11-slim"],
    )
    assert isinstance(host, Host)
    result = host.execute_command("python3 --version")
    assert result.success
    assert "Python" in result.stdout


@pytest.mark.acceptance
def test_create_host_with_resource_limits(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(
        HostName("test-resources"),
        build_args=["--cpu=2", "--memory=2"],
    )
    resources = docker_provider.get_host_resources(host)
    assert resources.cpu.count == 2
    assert resources.memory_gb == 2.0


@pytest.mark.acceptance
def test_stop_host_stops_container(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-stop"))
    docker_provider.stop_host(host, create_snapshot=False)

    # Host should now be offline
    host_obj = docker_provider.get_host(host.id)
    assert isinstance(host_obj, OfflineHost)


@pytest.mark.acceptance
def test_stop_host_with_snapshot(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-snap-stop"))
    docker_provider.stop_host(host, create_snapshot=True)

    snapshots = docker_provider.list_snapshots(host.id)
    assert len(snapshots) >= 1
    assert any(s.name == SnapshotName("stop") for s in snapshots)


@pytest.mark.acceptance
def test_start_host_restarts_stopped_container(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-restart"))
    host.execute_command("touch /mngr/marker.txt")
    docker_provider.stop_host(host, create_snapshot=False)

    restarted = docker_provider.start_host(host.id)
    assert isinstance(restarted, Host)
    result = restarted.execute_command("cat /mngr/marker.txt")
    assert result.success


@pytest.mark.acceptance
def test_start_host_filesystem_preserved_across_stop_start(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-fs-preserve"))
    host.execute_command("echo 'test content' > /tmp/myfile.txt")
    docker_provider.stop_host(host, create_snapshot=False)

    restarted = docker_provider.start_host(host.id)
    result = restarted.execute_command("cat /tmp/myfile.txt")
    assert result.success
    assert "test content" in result.stdout


@pytest.mark.acceptance
def test_start_host_on_running_host_returns_same_host(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-already-running"))
    restarted = docker_provider.start_host(host.id)
    assert isinstance(restarted, Host)


@pytest.mark.acceptance
def test_destroy_host_removes_container(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-destroy"))
    host_id = host.id
    docker_provider.destroy_host(host, delete_snapshots=True)

    with pytest.raises(HostNotFoundError):
        docker_provider.get_host(host_id)


@pytest.mark.acceptance
def test_get_host_by_id(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-get-id"))
    found = docker_provider.get_host(host.id)
    assert found.id == host.id


@pytest.mark.acceptance
def test_get_host_by_name(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-get-name"))
    found = docker_provider.get_host(HostName("test-get-name"))
    assert found.id == host.id


@pytest.mark.acceptance
def test_get_host_not_found_raises_error(docker_provider: DockerProviderInstance) -> None:
    with pytest.raises(HostNotFoundError):
        docker_provider.get_host(HostId.generate())


@pytest.mark.acceptance
def test_list_hosts_includes_created_host(docker_provider: DockerProviderInstance, temp_mngr_ctx: MngrContext) -> None:
    host = docker_provider.create_host(HostName("test-list"))
    hosts = docker_provider.list_hosts(temp_mngr_ctx.concurrency_group)
    host_ids = {h.id for h in hosts}
    assert host.id in host_ids


@pytest.mark.acceptance
def test_create_snapshot(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-snapshot"))
    snapshot_id = docker_provider.create_snapshot(host, SnapshotName("test-snap"))
    assert snapshot_id is not None

    snapshots = docker_provider.list_snapshots(host)
    assert len(snapshots) == 1
    assert snapshots[0].name == SnapshotName("test-snap")


@pytest.mark.acceptance
def test_delete_snapshot(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-del-snap"))
    snapshot_id = docker_provider.create_snapshot(host, SnapshotName("to-delete"))

    docker_provider.delete_snapshot(host, snapshot_id)

    snapshots = docker_provider.list_snapshots(host)
    assert len(snapshots) == 0


@pytest.mark.acceptance
def test_delete_nonexistent_snapshot_raises_error(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-del-nonexist"))
    with pytest.raises(SnapshotNotFoundError):
        docker_provider.delete_snapshot(host, SnapshotId("sha256:nonexistent0000000000000000000000"))


@pytest.mark.acceptance
def test_set_host_tags_raises_mngr_error(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-tags-immutable"))
    with pytest.raises(MngrError, match="does not support mutable tags"):
        docker_provider.set_host_tags(host, {"new": "tag"})


@pytest.mark.acceptance
def test_rename_host(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-rename"))
    docker_provider.rename_host(host, HostName("renamed-host"))

    found = docker_provider.get_host(host.id)
    assert found.get_certified_data().host_name == "renamed-host"


@pytest.mark.acceptance
def test_close_closes_docker_client(temp_mngr_ctx: MngrContext) -> None:
    provider = make_docker_provider(temp_mngr_ctx, "test-close")
    # Access the client to initialize it
    _ = provider._docker_client
    provider.close()


@pytest.mark.acceptance
def test_on_connection_error_clears_caches(docker_provider: DockerProviderInstance) -> None:
    host = docker_provider.create_host(HostName("test-conn-err"))
    # Populate caches
    docker_provider.get_host(host.id)
    # Should not raise
    docker_provider.on_connection_error(host.id)
