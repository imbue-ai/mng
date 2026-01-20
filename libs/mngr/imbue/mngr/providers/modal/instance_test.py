"""Tests for the ModalProviderInstance.

These tests require Modal credentials and network access to run. They are marked
with @pytest.mark.modal and are skipped by default. To run them:

    pytest -m modal --timeout=180

Or to run all tests including Modal tests:

    pytest --timeout=180
"""

from pathlib import Path

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.providers.modal.instance import ModalProviderInstance

# Skip all tests in this module if Modal is not available
pytest.importorskip("modal")


def make_modal_provider(mngr_ctx: MngrContext, app_name: str) -> ModalProviderInstance:
    """Create a ModalProviderInstance for testing."""
    # 5 minutes timeout for tests
    return ModalProviderInstance(
        name=ProviderInstanceName("modal-test"),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        app_name=app_name,
        default_timeout=300,
        default_cpu=0.5,
        default_memory=0.5,
    )


@pytest.fixture
def modal_provider(temp_mngr_ctx: MngrContext, mngr_test_id: str) -> ModalProviderInstance:
    """Create a ModalProviderInstance with a unique app name for test isolation."""
    return make_modal_provider(temp_mngr_ctx, f"mngr-test-{mngr_test_id}")


# =============================================================================
# Basic property tests (no network required)
# =============================================================================


def test_modal_provider_name(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should have the correct name."""
    assert modal_provider.name == ProviderInstanceName("modal-test")


def test_modal_provider_supports_snapshots(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should support snapshots via sandbox.snapshot_filesystem()."""
    assert modal_provider.supports_snapshots is True


def test_modal_provider_does_not_support_volumes(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should not support volumes."""
    assert modal_provider.supports_volumes is False


def test_modal_provider_supports_mutable_tags(modal_provider: ModalProviderInstance) -> None:
    """Modal provider supports mutable tags via Modal's sandbox.set_tags() API."""
    assert modal_provider.supports_mutable_tags is True


def test_list_volumes_returns_empty_list(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should return empty list for volumes."""
    volumes = modal_provider.list_volumes()
    assert volumes == []


# =============================================================================
# Build args parsing tests (no network required)
# =============================================================================


def test_parse_build_args_empty(modal_provider: ModalProviderInstance) -> None:
    """Empty build args should return default config."""
    config = modal_provider._parse_build_args(None)
    assert config.gpu is None
    # These values come from the modal_provider fixture defaults
    assert config.cpu == 0.5
    assert config.memory == 0.5
    assert config.image is None
    assert config.timeout == 300

    config = modal_provider._parse_build_args([])
    assert config.gpu is None


def test_parse_build_args_key_value_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse simple key=value format."""
    config = modal_provider._parse_build_args(["gpu=h100", "cpu=2", "memory=8"])
    assert config.gpu == "h100"
    assert config.cpu == 2.0
    assert config.memory == 8.0


def test_parse_build_args_flag_equals_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse --key=value format."""
    config = modal_provider._parse_build_args(["--gpu=a100", "--cpu=4", "--memory=16"])
    assert config.gpu == "a100"
    assert config.cpu == 4.0
    assert config.memory == 16.0


def test_parse_build_args_flag_space_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse --key value format (two separate args)."""
    config = modal_provider._parse_build_args(["--gpu", "t4", "--cpu", "1", "--memory", "2"])
    assert config.gpu == "t4"
    assert config.cpu == 1.0
    assert config.memory == 2.0


def test_parse_build_args_mixed_formats(modal_provider: ModalProviderInstance) -> None:
    """Should parse mixed formats in same call."""
    config = modal_provider._parse_build_args(["gpu=h100", "--cpu=2", "--memory", "4"])
    assert config.gpu == "h100"
    assert config.cpu == 2.0
    assert config.memory == 4.0


def test_parse_build_args_image_and_timeout(modal_provider: ModalProviderInstance) -> None:
    """Should parse image and timeout arguments."""
    config = modal_provider._parse_build_args(["image=python:3.11-slim", "timeout=3600"])
    assert config.image == "python:3.11-slim"
    assert config.timeout == 3600


def test_parse_build_args_unknown_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Unknown build args should raise MngrError."""
    with pytest.raises(MngrError) as exc_info:
        modal_provider._parse_build_args(["gpu=h100", "unknown=value"])
    assert "Unknown build arguments" in str(exc_info.value)


def test_parse_build_args_invalid_type_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Invalid type for numeric args should raise MngrError."""
    with pytest.raises(MngrError):
        modal_provider._parse_build_args(["cpu=not_a_number"])


def test_parse_build_args_value_with_equals(modal_provider: ModalProviderInstance) -> None:
    """Should handle values containing equals signs."""
    # Image names can contain = in tags
    config = modal_provider._parse_build_args(["--image=myregistry.com/image:tag=v1"])
    assert config.image == "myregistry.com/image:tag=v1"


# =============================================================================
# Acceptance tests (require Modal network access)
# =============================================================================


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_create_host_creates_sandbox_with_ssh(modal_provider: ModalProviderInstance) -> None:
    """Creating a host should create a Modal sandbox with SSH access."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))

        # Verify host was created
        assert host.id is not None
        assert host.connector is not None

        # Verify SSH connector type
        assert host.connector.connector_cls_name == "SSHConnector"

        # Verify we can execute commands via SSH
        result = host.execute_command("echo 'hello from modal'")
        assert result.success
        assert "hello from modal" in result.stdout

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_get_host_by_id(modal_provider: ModalProviderInstance) -> None:
    """Should be able to get a host by its ID."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Get the same host by ID
        retrieved_host = modal_provider.get_host(host_id)
        assert retrieved_host.id == host_id

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_get_host_by_name(modal_provider: ModalProviderInstance) -> None:
    """Should be able to get a host by its name."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Get the same host by name
        retrieved_host = modal_provider.get_host(HostName("test-host"))
        assert retrieved_host.id == host_id

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_list_hosts_includes_created_host(modal_provider: ModalProviderInstance) -> None:
    """Created host should appear in list_hosts."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))

        hosts = modal_provider.list_hosts()
        host_ids = [h.id for h in hosts]
        assert host.id in host_ids

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_destroy_host_removes_sandbox(modal_provider: ModalProviderInstance) -> None:
    """Destroying a host should remove it from the provider."""
    host = modal_provider.create_host(HostName("test-host"))
    host_id = host.id

    modal_provider.destroy_host(host)

    # Host should no longer be found
    with pytest.raises(HostNotFoundError):
        modal_provider.get_host(host_id)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_get_host_resources(modal_provider: ModalProviderInstance) -> None:
    """Should be able to get resource information for a host."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))
        resources = modal_provider.get_host_resources(host)

        assert resources.cpu.count >= 1
        assert resources.memory_gb >= 0.5

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_get_and_set_host_tags(modal_provider: ModalProviderInstance) -> None:
    """Should be able to get and set tags on a host."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))

        # Initially no tags
        tags = modal_provider.get_host_tags(host)
        assert tags == {}

        # Set some tags
        modal_provider.set_host_tags(host, {"env": "test", "team": "backend"})
        tags = modal_provider.get_host_tags(host)
        assert tags == {"env": "test", "team": "backend"}

        # Add a tag
        modal_provider.add_tags_to_host(host, {"version": "1.0"})
        tags = modal_provider.get_host_tags(host)
        assert len(tags) == 3
        assert tags["version"] == "1.0"

        # Remove a tag
        modal_provider.remove_tags_from_host(host, ["team"])
        tags = modal_provider.get_host_tags(host)
        assert "team" not in tags
        assert len(tags) == 2

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_create_and_list_snapshots(modal_provider: ModalProviderInstance) -> None:
    """Should be able to create and list snapshots."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))

        # Initially no snapshots
        snapshots = modal_provider.list_snapshots(host)
        assert snapshots == []

        # Create a snapshot
        snapshot_id = modal_provider.create_snapshot(host, SnapshotName("test-snapshot"))
        assert snapshot_id is not None

        # Verify it appears in the list
        snapshots = modal_provider.list_snapshots(host)
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot_id
        assert snapshots[0].name == SnapshotName("test-snapshot")
        assert snapshots[0].recency_idx == 0

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_list_snapshots_returns_empty_initially(modal_provider: ModalProviderInstance) -> None:
    """list_snapshots should return empty list for a new host."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))
        snapshots = modal_provider.list_snapshots(host)
        assert snapshots == []

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_delete_snapshot(modal_provider: ModalProviderInstance) -> None:
    """Should be able to delete a snapshot."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))

        # Create a snapshot
        snapshot_id = modal_provider.create_snapshot(host)
        assert len(modal_provider.list_snapshots(host)) == 1

        # Delete it
        modal_provider.delete_snapshot(host, snapshot_id)
        assert len(modal_provider.list_snapshots(host)) == 0

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_delete_nonexistent_snapshot_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Deleting a nonexistent snapshot should raise SnapshotNotFoundError."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))

        fake_id = SnapshotId.generate()
        with pytest.raises(SnapshotNotFoundError):
            modal_provider.delete_snapshot(host, fake_id)

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(300)
def test_start_host_restores_from_snapshot(modal_provider: ModalProviderInstance) -> None:
    """start_host with a snapshot_id should restore a terminated host from the snapshot."""
    host = None
    restored_host = None
    try:
        # Create a host and write a marker file
        host = modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Write a marker file to verify restoration
        result = host.execute_command("echo 'snapshot-marker' > /tmp/marker.txt")
        assert result.success

        # Create a snapshot
        snapshot_id = modal_provider.create_snapshot(host, SnapshotName("test-restore"))

        # Verify snapshot exists
        snapshots = modal_provider.list_snapshots(host)
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot_id

        # Stop the host (terminates the sandbox)
        modal_provider.stop_host(host)

        # Restore from snapshot
        restored_host = modal_provider.start_host(host_id, snapshot_id=snapshot_id)

        # Verify the host was restored with the same ID
        assert restored_host.id == host_id

        # Verify the marker file exists (proving we restored from snapshot)
        result = restored_host.execute_command("cat /tmp/marker.txt")
        assert result.success
        assert "snapshot-marker" in result.stdout

    finally:
        if restored_host:
            modal_provider.destroy_host(restored_host)
        elif host:
            modal_provider.destroy_host(host)
        else:
            pass


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_start_host_on_running_host(modal_provider: ModalProviderInstance) -> None:
    """start_host on a running host should return the same host."""
    host = None
    try:
        host = modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Starting a running host should just return it
        started_host = modal_provider.start_host(host)
        assert started_host.id == host_id

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.modal
@pytest.mark.timeout(180)
def test_start_host_on_stopped_host_raises_error(modal_provider: ModalProviderInstance) -> None:
    """start_host on a terminated host should raise an error."""
    host = modal_provider.create_host(HostName("test-host"))
    host_id = host.id

    # Stop/destroy the host
    modal_provider.stop_host(host)

    # Trying to start it should fail
    with pytest.raises(MngrError):
        modal_provider.start_host(host_id)


@pytest.mark.modal
def test_get_host_not_found_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Getting a non-existent host should raise HostNotFoundError."""
    fake_id = HostId.generate()
    with pytest.raises(HostNotFoundError):
        modal_provider.get_host(fake_id)


@pytest.mark.modal
def test_get_host_by_name_not_found_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Getting a non-existent host by name should raise HostNotFoundError."""
    with pytest.raises(HostNotFoundError):
        modal_provider.get_host(HostName("nonexistent-host"))
