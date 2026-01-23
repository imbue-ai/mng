"""Tests for error classes."""

from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import AgentNotFoundOnHostError
from imbue.mngr.errors import HostNameConflictError
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import HostNotRunningError
from imbue.mngr.errors import HostNotStoppedError
from imbue.mngr.errors import ImageNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ProviderInstanceNotFoundError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.errors import SnapshotsNotSupportedError
from imbue.mngr.errors import TagLimitExceededError
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId


def test_agent_not_found_error_sets_agent_identifier() -> None:
    """AgentNotFoundError should set agent_identifier attribute."""
    agent_id = AgentId.generate()
    error = AgentNotFoundError(str(agent_id))
    assert error.agent_identifier == str(agent_id)
    assert str(agent_id) in str(error)


def test_host_not_found_error_with_host_id() -> None:
    """HostNotFoundError should work with HostId."""
    host_id = HostId.generate()
    error = HostNotFoundError(host_id)
    assert error.host == host_id
    assert "Host not found" in str(error)


def test_host_not_found_error_with_host_name() -> None:
    """HostNotFoundError should work with HostName."""
    host_name = HostName("test-host")
    error = HostNotFoundError(host_name)
    assert error.host == host_name
    assert "Host not found" in str(error)


def test_image_not_found_error_sets_image() -> None:
    """ImageNotFoundError should set image attribute."""
    image = ImageReference("nonexistent:tag")
    error = ImageNotFoundError(image)
    assert error.image == image
    assert "Image not found" in str(error)


def test_host_name_conflict_error_sets_name() -> None:
    """HostNameConflictError should set name attribute."""
    name = HostName("duplicate")
    error = HostNameConflictError(name)
    assert error.name == name
    assert "already exists" in str(error)


def test_host_not_running_error_includes_state() -> None:
    """HostNotRunningError should include state in message."""
    host_id = HostId.generate()
    error = HostNotRunningError(host_id, HostState.STOPPED)
    assert error.host_id == host_id
    assert error.state == HostState.STOPPED
    assert "STOPPED" in str(error)


def test_host_not_stopped_error_includes_state() -> None:
    """HostNotStoppedError should include state in message."""
    host_id = HostId.generate()
    error = HostNotStoppedError(host_id, HostState.RUNNING)
    assert error.host_id == host_id
    assert error.state == HostState.RUNNING
    assert "RUNNING" in str(error)


def test_snapshot_not_found_error_sets_snapshot_id() -> None:
    """SnapshotNotFoundError should set snapshot_id attribute."""
    snapshot_id = SnapshotId.generate()
    error = SnapshotNotFoundError(snapshot_id)
    assert error.snapshot_id == snapshot_id
    assert "Snapshot not found" in str(error)


def test_snapshots_not_supported_error_includes_provider() -> None:
    """SnapshotsNotSupportedError should include provider name."""
    provider_name = ProviderInstanceName("test-provider")
    error = SnapshotsNotSupportedError(provider_name)
    assert error.provider_name == provider_name
    assert "test-provider" in str(error)


def test_tag_limit_exceeded_error_includes_limit_and_actual() -> None:
    """TagLimitExceededError should include both limit and actual."""
    error = TagLimitExceededError(limit=10, actual=15)
    assert error.limit == 10
    assert error.actual == 15
    assert "10" in str(error)
    assert "15" in str(error)


def test_agent_not_found_on_host_error_sets_both_ids() -> None:
    """AgentNotFoundOnHostError should set agent_id and host_id attributes."""
    agent_id = AgentId.generate()
    host_id = HostId.generate()
    error = AgentNotFoundOnHostError(agent_id, host_id)
    assert error.agent_id == agent_id
    assert error.host_id == host_id
    assert str(agent_id) in str(error)
    assert str(host_id) in str(error)


def test_provider_instance_not_found_error_sets_provider_name() -> None:
    """ProviderInstanceNotFoundError should set provider_name attribute."""
    provider_name = ProviderInstanceName("test-provider")
    error = ProviderInstanceNotFoundError(provider_name)
    assert error.provider_name == provider_name
    assert "test-provider" in str(error)


def test_mngr_error_has_user_help_text_attribute() -> None:
    """MngrError base class should have user_help_text attribute."""
    error = MngrError("test error")
    assert hasattr(error, "user_help_text")
    assert error.user_help_text is None


def test_user_input_error_has_user_help_text() -> None:
    """UserInputError should have user_help_text for CLI help."""
    error = UserInputError("invalid input")
    assert error.user_help_text is not None
    assert "mngr --help" in error.user_help_text


def test_agent_not_found_error_has_user_help_text() -> None:
    """AgentNotFoundError should have user_help_text for listing agents."""
    agent_id = AgentId.generate()
    error = AgentNotFoundError(str(agent_id))
    assert error.user_help_text is not None
    assert "mngr list" in error.user_help_text


def test_host_not_found_error_has_user_help_text() -> None:
    """HostNotFoundError should have user_help_text."""
    host_name = HostName("test-host")
    error = HostNotFoundError(host_name)
    assert error.user_help_text is not None
    assert "mngr list" in error.user_help_text


def test_host_name_conflict_error_has_user_help_text() -> None:
    """HostNameConflictError should have user_help_text."""
    name = HostName("duplicate")
    error = HostNameConflictError(name)
    assert error.user_help_text is not None
    assert "mngr destroy" in error.user_help_text


def test_host_not_running_error_has_user_help_text() -> None:
    """HostNotRunningError should have user_help_text."""
    host_id = HostId.generate()
    error = HostNotRunningError(host_id, HostState.STOPPED)
    assert error.user_help_text is not None
    assert "mngr start" in error.user_help_text


def test_host_not_stopped_error_has_user_help_text() -> None:
    """HostNotStoppedError should have user_help_text."""
    host_id = HostId.generate()
    error = HostNotStoppedError(host_id, HostState.RUNNING)
    assert error.user_help_text is not None
    assert "mngr stop" in error.user_help_text


def test_snapshot_not_found_error_has_user_help_text() -> None:
    """SnapshotNotFoundError should have user_help_text."""
    snapshot_id = SnapshotId.generate()
    error = SnapshotNotFoundError(snapshot_id)
    assert error.user_help_text is not None
    assert "snapshot" in error.user_help_text.lower()


def test_provider_instance_not_found_error_has_user_help_text() -> None:
    """ProviderInstanceNotFoundError should have user_help_text."""
    provider_name = ProviderInstanceName("test-provider")
    error = ProviderInstanceNotFoundError(provider_name)
    assert error.user_help_text is not None
    assert "provider" in error.user_help_text.lower()
