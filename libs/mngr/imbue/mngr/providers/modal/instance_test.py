"""Tests for the ModalProviderInstance.

These tests require Modal credentials and network access to run. They are marked
with @pytest.mark.acceptance and are skipped by default. To run them:

    pytest -m modal --timeout=180

Or to run all tests including Modal tests:

    pytest --timeout=180
"""

from typing import cast
from unittest.mock import patch

import modal.exception
import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ModalAuthError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.providers.modal.backend import ModalProviderBackend
from imbue.mngr.providers.modal.instance import ModalProviderInstance
from imbue.mngr.providers.modal.instance import TAG_HOST_ID
from imbue.mngr.providers.modal.instance import TAG_HOST_NAME
from imbue.mngr.providers.modal.instance import TAG_USER_PREFIX
from imbue.mngr.providers.modal.instance import build_sandbox_tags
from imbue.mngr.providers.modal.instance import parse_sandbox_tags


# =============================================================================
# Unit tests for sandbox tag helper functions
# =============================================================================


def test_build_sandbox_tags_with_no_user_tags() -> None:
    """build_sandbox_tags with no user tags should only include host_id and host_name."""
    host_id = HostId.generate()
    name = HostName("test-host")

    tags = build_sandbox_tags(host_id, name, None)

    assert tags == {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }


def test_build_sandbox_tags_with_empty_user_tags() -> None:
    """build_sandbox_tags with empty user tags dict should only include host_id and host_name."""
    host_id = HostId.generate()
    name = HostName("test-host")

    tags = build_sandbox_tags(host_id, name, {})

    assert tags == {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }


def test_build_sandbox_tags_with_user_tags() -> None:
    """build_sandbox_tags with user tags should prefix them with TAG_USER_PREFIX."""
    host_id = HostId.generate()
    name = HostName("test-host")
    user_tags = {"env": "production", "team": "backend"}

    tags = build_sandbox_tags(host_id, name, user_tags)

    assert tags[TAG_HOST_ID] == str(host_id)
    assert tags[TAG_HOST_NAME] == str(name)
    assert tags[TAG_USER_PREFIX + "env"] == "production"
    assert tags[TAG_USER_PREFIX + "team"] == "backend"
    assert len(tags) == 4


def test_parse_sandbox_tags_extracts_host_id_and_name() -> None:
    """parse_sandbox_tags should extract host_id and name from tags."""
    host_id = HostId.generate()
    name = HostName("test-host")
    tags = {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }

    parsed_host_id, parsed_name, parsed_user_tags = parse_sandbox_tags(tags)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_user_tags == {}


def test_parse_sandbox_tags_extracts_user_tags() -> None:
    """parse_sandbox_tags should extract user tags and strip the prefix."""
    host_id = HostId.generate()
    name = HostName("test-host")
    tags = {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
        TAG_USER_PREFIX + "env": "staging",
        TAG_USER_PREFIX + "version": "1.0.0",
    }

    parsed_host_id, parsed_name, parsed_user_tags = parse_sandbox_tags(tags)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_user_tags == {"env": "staging", "version": "1.0.0"}


def test_build_and_parse_sandbox_tags_roundtrip() -> None:
    """Building and parsing tags should round-trip correctly."""
    host_id = HostId.generate()
    name = HostName("my-test-host")
    user_tags = {"key1": "value1", "key2": "value2"}

    built_tags = build_sandbox_tags(host_id, name, user_tags)
    parsed_host_id, parsed_name, parsed_user_tags = parse_sandbox_tags(built_tags)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_user_tags == user_tags


def make_modal_provider(mngr_ctx: MngrContext, app_name: str) -> ModalProviderInstance:
    """Create a ModalProviderInstance for testing."""
    # Use the backend to properly construct the instance with app and backend_cls
    instance = ModalProviderBackend.build_provider_instance(
        name=ProviderInstanceName("modal-test"),
        instance_configuration={
            "app_name": app_name,
            "host_dir": "/mngr",
            "default_timeout": 300,
            "default_cpu": 0.5,
            "default_memory": 0.5,
        },
        mngr_ctx=mngr_ctx,
    )
    return cast(ModalProviderInstance, instance)


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


def test_handle_modal_auth_error_decorator_converts_auth_error_to_modal_auth_error(
    modal_provider: ModalProviderInstance,
) -> None:
    """The @handle_modal_auth_error decorator should convert modal.exception.AuthError to ModalAuthError."""
    # Mock the _get_modal_app method to raise an AuthError
    with patch.object(modal_provider, "_get_modal_app") as mock_get_app:
        mock_get_app.side_effect = modal.exception.AuthError("Token missing")

        # list_hosts is decorated with @handle_modal_auth_error
        with pytest.raises(ModalAuthError) as exc_info:
            modal_provider.list_hosts()

        # Verify the error message contains helpful information
        error_message = str(exc_info.value)
        assert "Modal authentication failed" in error_message
        assert "--disable-plugin modal" in error_message
        assert "https://modal.com/docs/reference/modal.config" in error_message

        # Verify the original AuthError is chained
        assert isinstance(exc_info.value.__cause__, modal.exception.AuthError)


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


def test_parse_build_args_region(modal_provider: ModalProviderInstance) -> None:
    """Should parse region argument."""
    config = modal_provider._parse_build_args(["region=us-east"])
    assert config.region == "us-east"

    config = modal_provider._parse_build_args(["--region=eu-west"])
    assert config.region == "eu-west"

    config = modal_provider._parse_build_args(["--region", "us-west"])
    assert config.region == "us-west"


def test_parse_build_args_region_default_is_none(modal_provider: ModalProviderInstance) -> None:
    """Region should default to None (auto-select)."""
    config = modal_provider._parse_build_args([])
    assert config.region is None

    config = modal_provider._parse_build_args(["cpu=2"])
    assert config.region is None


# =============================================================================
# Acceptance tests (require Modal network access)
# =============================================================================


@pytest.mark.acceptance
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

        # Verify output capture is working (Modal should emit some output during host creation)
        captured_output = modal_provider.get_captured_output()
        assert isinstance(captured_output, str)

    finally:
        if host:
            modal_provider.destroy_host(host)


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_destroy_host_removes_sandbox(modal_provider: ModalProviderInstance) -> None:
    """Destroying a host should remove it from the provider."""
    host = modal_provider.create_host(HostName("test-host"))
    host_id = host.id

    modal_provider.destroy_host(host)

    # Host should no longer be found
    with pytest.raises(HostNotFoundError):
        modal_provider.get_host(host_id)


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
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


@pytest.mark.acceptance
def test_get_host_not_found_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Getting a non-existent host should raise HostNotFoundError."""
    fake_id = HostId.generate()
    with pytest.raises(HostNotFoundError):
        modal_provider.get_host(fake_id)


@pytest.mark.acceptance
def test_get_host_by_name_not_found_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Getting a non-existent host by name should raise HostNotFoundError."""
    with pytest.raises(HostNotFoundError):
        modal_provider.get_host(HostName("nonexistent-host"))
