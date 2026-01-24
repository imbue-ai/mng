"""Tests for the SSHProviderInstance."""

from pathlib import Path

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import SnapshotsNotSupportedError
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.providers.ssh.backend import SSHHostConfig
from imbue.mngr.providers.ssh.instance import SSHProviderInstance


def make_ssh_provider(
    temp_host_dir: Path,
    temp_mngr_ctx: MngrContext,
    hosts: dict[str, SSHHostConfig] | None = None,
) -> SSHProviderInstance:
    """Create an SSHProviderInstance for testing."""
    if hosts is None:
        hosts = {
            "test-host": SSHHostConfig(address="localhost", port=22),
        }
    return SSHProviderInstance(
        name=ProviderInstanceName("ssh-test"),
        host_dir=Path("/tmp/mngr"),
        mngr_ctx=temp_mngr_ctx,
        hosts=hosts,
        local_state_dir=temp_host_dir,
    )


def test_ssh_provider_name(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    assert provider.name == ProviderInstanceName("ssh-test")


def test_ssh_provider_does_not_support_snapshots(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    assert provider.supports_snapshots is False


def test_ssh_provider_does_not_support_volumes(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    assert provider.supports_volumes is False


def test_ssh_provider_does_not_support_mutable_tags(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    assert provider.supports_mutable_tags is False


def test_create_snapshot_raises_error(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    with pytest.raises(SnapshotsNotSupportedError):
        provider.create_snapshot(HostId.generate())


def test_list_snapshots_returns_empty_list(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    snapshots = provider.list_snapshots(HostId.generate())
    assert snapshots == []


def test_delete_snapshot_raises_error(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    with pytest.raises(SnapshotsNotSupportedError):
        provider.delete_snapshot(HostId.generate(), SnapshotId.generate())


def test_list_volumes_returns_empty_list(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    volumes = provider.list_volumes()
    assert volumes == []


def test_get_host_tags_returns_empty_dict(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    tags = provider.get_host_tags(HostId.generate())
    assert tags == {}


def test_list_hosts_returns_empty_when_no_hosts_registered(
    temp_host_dir: Path, temp_mngr_ctx: MngrContext
) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    hosts = provider.list_hosts()
    assert hosts == []


def test_get_host_not_found_for_unknown_id(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    with pytest.raises(HostNotFoundError):
        provider.get_host(HostId.generate())


def test_get_host_not_found_for_unknown_name(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    with pytest.raises(HostNotFoundError):
        provider.get_host(HostName("nonexistent"))


def test_create_host_fails_for_unconfigured_host(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    with pytest.raises(UserInputError) as exc_info:
        provider.create_host(HostName("unknown-host"))
    assert "not in the SSH host pool configuration" in str(exc_info.value)


def test_host_dir_is_set_correctly(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = SSHProviderInstance(
        name=ProviderInstanceName("ssh-test"),
        host_dir=Path("/custom/remote/path"),
        mngr_ctx=temp_mngr_ctx,
        hosts={},
        local_state_dir=temp_host_dir,
    )
    assert provider.host_dir == Path("/custom/remote/path")


def test_local_state_dir_is_set_correctly(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    assert provider.local_state_dir == temp_host_dir


def test_stop_host_is_noop(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """stop_host should be a no-op for SSH provider."""
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    # Should not raise
    provider.stop_host(HostId.generate())


def test_get_host_resources_returns_defaults(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """get_host_resources should return sensible defaults."""
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)

    # Create a mock host interface-like object with just an id
    class MockHost:
        id = HostId.generate()

    resources = provider.get_host_resources(MockHost())  # ty: ignore[invalid-argument-type]
    assert resources.cpu.count >= 1
    assert resources.memory_gb >= 0


def test_close_is_noop(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """close should be a no-op for SSH provider."""
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    # Should not raise
    provider.close()


def test_rename_host_with_nonexistent_host_raises_error(
    temp_host_dir: Path, temp_mngr_ctx: MngrContext
) -> None:
    """rename_host should raise HostNotFoundError for non-existent host."""
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx)
    fake_host_id = HostId.generate()

    with pytest.raises(HostNotFoundError):
        provider.rename_host(fake_host_id, HostName("test-host"))


def test_rename_host_to_unconfigured_name_raises_error(
    temp_host_dir: Path, temp_mngr_ctx: MngrContext
) -> None:
    """rename_host to unconfigured name should raise UserInputError."""
    hosts = {
        "host1": SSHHostConfig(address="localhost", port=22),
        "host2": SSHHostConfig(address="localhost", port=2222),
    }
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx, hosts=hosts)

    # Manually create state for host1 (simulating a registered host)
    host_id = HostId.generate()
    state = {"host_id": str(host_id), "host_name": "host1"}
    provider._write_host_state("host1", state)

    with pytest.raises(UserInputError) as exc_info:
        provider.rename_host(host_id, HostName("nonexistent-host"))
    assert "not in SSH host pool configuration" in str(exc_info.value)


def test_rename_host_updates_state_files(
    temp_host_dir: Path, temp_mngr_ctx: MngrContext
) -> None:
    """rename_host should update state files correctly."""
    hosts = {
        "host1": SSHHostConfig(address="localhost", port=22),
        "host2": SSHHostConfig(address="localhost", port=2222),
    }
    provider = make_ssh_provider(temp_host_dir, temp_mngr_ctx, hosts=hosts)

    # Manually create state for host1 (simulating a registered host)
    host_id = HostId.generate()
    state = {"host_id": str(host_id), "host_name": "host1"}
    provider._write_host_state("host1", state)

    # Verify old state exists
    old_state_path = provider._get_host_state_path("host1")
    assert old_state_path.exists()

    # Rename host1 to host2
    renamed_host = provider.rename_host(host_id, HostName("host2"))

    # Verify old state is deleted and new state exists
    assert not old_state_path.exists()
    new_state_path = provider._get_host_state_path("host2")
    assert new_state_path.exists()

    # Verify new state has correct content
    new_state = provider._read_host_state("host2")
    assert new_state is not None
    assert new_state["host_id"] == str(host_id)
    assert new_state["host_name"] == "host2"

    # Verify returned host has correct ID
    assert renamed_host.id == host_id
