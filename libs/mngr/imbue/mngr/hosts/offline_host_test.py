"""Unit tests for OfflineHost implementation."""

from datetime import datetime
from datetime import timezone
from unittest.mock import create_autospec

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.offline_host import OfflineHost
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName


@pytest.fixture
def mock_provider():
    """Create a mock provider instance."""
    provider = create_autospec(ProviderInstanceInterface, instance=True)
    provider.name = ProviderInstanceName("test-provider")
    provider.supports_snapshots = True
    provider.list_snapshots.return_value = []
    provider.get_host_tags.return_value = {"env": "test"}
    provider.list_persisted_agent_data_for_host.return_value = []
    return provider


@pytest.fixture
def mock_mngr_ctx():
    """Create a mock MngrContext."""
    return create_autospec(MngrContext, instance=True)


@pytest.fixture
def offline_host(mock_provider, mock_mngr_ctx):
    """Create an OfflineHost instance for testing."""
    certified_data = CertifiedHostData(
        idle_mode=IdleMode.SSH,
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.SSH, ActivitySource.AGENT),
        image="test-image:latest",
        plugin={"my_plugin": {"key": "value"}},
    )
    return OfflineHost(
        id=HostId.generate(),
        certified_host_data=certified_data,
        is_online=False,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )


def test_get_activity_config_returns_config_from_certified_data(offline_host: OfflineHost):
    """Test that get_activity_config returns the correct ActivityConfig."""
    config = offline_host.get_activity_config()

    assert isinstance(config, ActivityConfig)
    assert config.idle_mode == IdleMode.SSH
    assert config.idle_timeout_seconds == 3600
    assert config.activity_sources == (ActivitySource.SSH, ActivitySource.AGENT)


def test_get_reported_activity_time_returns_none(offline_host: OfflineHost):
    """Test that get_reported_activity_time always returns None for offline hosts."""
    result = offline_host.get_reported_activity_time(ActivitySource.SSH)
    assert result is None

    result = offline_host.get_reported_activity_time(ActivitySource.BOOT)
    assert result is None


def test_get_all_certified_data_returns_stored_data(offline_host: OfflineHost):
    """Test that get_all_certified_data returns the certified host data."""
    data = offline_host.get_all_certified_data()

    assert isinstance(data, CertifiedHostData)
    assert data.image == "test-image:latest"
    assert data.idle_mode == IdleMode.SSH


def test_get_plugin_data_returns_plugin_data_when_present(offline_host: OfflineHost):
    """Test that get_plugin_data returns data for existing plugins."""
    data = offline_host.get_plugin_data("my_plugin")
    assert data == {"key": "value"}


def test_get_plugin_data_returns_empty_dict_when_missing(offline_host: OfflineHost):
    """Test that get_plugin_data returns empty dict for non-existent plugins."""
    data = offline_host.get_plugin_data("nonexistent_plugin")
    assert data == {}


def test_get_snapshots_delegates_to_provider(offline_host: OfflineHost, mock_provider):
    """Test that get_snapshots calls the provider's list_snapshots method."""
    expected_snapshots = [
        SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("snap1"),
            created_at=datetime.now(timezone.utc),
        )
    ]
    mock_provider.list_snapshots.return_value = expected_snapshots

    snapshots = offline_host.get_snapshots()

    assert snapshots == expected_snapshots
    mock_provider.list_snapshots.assert_called_once_with(offline_host)


def test_get_image_returns_image_from_certified_data(offline_host: OfflineHost):
    """Test that get_image returns the image from certified data."""
    image = offline_host.get_image()
    assert image == "test-image:latest"


def test_get_tags_delegates_to_provider(offline_host: OfflineHost, mock_provider):
    """Test that get_tags calls the provider's get_host_tags method."""
    tags = offline_host.get_tags()

    assert tags == {"env": "test"}
    mock_provider.get_host_tags.assert_called_once_with(offline_host)


def test_get_agent_references_returns_refs_from_provider(offline_host: OfflineHost, mock_provider):
    """Test that get_agent_references loads agent data from provider and populates certified_data."""
    agent_id_1 = AgentId.generate()
    agent_id_2 = AgentId.generate()
    agent_data_1 = {"id": str(agent_id_1), "name": "my-agent", "type": "claude", "permissions": ["read", "write"]}
    agent_data_2 = {"id": str(agent_id_2), "name": "other-agent", "type": "codex"}
    mock_provider.list_persisted_agent_data_for_host.return_value = [agent_data_1, agent_data_2]

    refs = offline_host.get_agent_references()

    assert len(refs) == 2
    assert refs[0].agent_id == agent_id_1
    assert refs[0].agent_name == AgentName("my-agent")
    assert refs[0].host_id == offline_host.id
    assert refs[0].provider_name == ProviderInstanceName("test-provider")
    # Verify certified_data is populated with full agent data
    assert refs[0].certified_data == agent_data_1
    assert refs[0].agent_type == "claude"
    assert refs[0].permissions == ("read", "write")

    assert refs[1].agent_id == agent_id_2
    assert refs[1].agent_name == AgentName("other-agent")
    assert refs[1].certified_data == agent_data_2
    assert refs[1].agent_type == "codex"
    assert refs[1].permissions == ()


def test_get_agent_references_returns_empty_list_on_error(offline_host: OfflineHost, mock_provider):
    """Test that get_agent_references returns empty list when provider raises KeyError."""
    mock_provider.list_persisted_agent_data_for_host.return_value = [
        {"invalid_key": "missing id and name"}
    ]

    refs = offline_host.get_agent_references()
    assert refs == []


def test_get_agent_references_returns_empty_list_on_value_error(offline_host: OfflineHost, mock_provider):
    """Test that get_agent_references returns empty list when provider raises ValueError."""
    mock_provider.list_persisted_agent_data_for_host.side_effect = ValueError("Invalid data")

    refs = offline_host.get_agent_references()
    assert refs == []


def test_get_idle_seconds_returns_infinity(offline_host: OfflineHost):
    """Test that get_idle_seconds returns infinity for offline hosts."""
    idle = offline_host.get_idle_seconds()
    assert idle == float("inf")


def test_get_permissions_returns_empty_list_when_no_agents(offline_host: OfflineHost):
    """Test that get_permissions returns empty list when no agents exist."""
    permissions = offline_host.get_permissions()
    assert permissions == []


def test_get_permissions_returns_permissions_from_agents(offline_host: OfflineHost, mock_provider):
    """Test that get_permissions returns union of all agent permissions from persisted data."""
    agent_id_1 = AgentId.generate()
    agent_id_2 = AgentId.generate()
    mock_provider.list_persisted_agent_data_for_host.return_value = [
        {"id": str(agent_id_1), "name": "agent-1", "permissions": ["read", "write"]},
        {"id": str(agent_id_2), "name": "agent-2", "permissions": ["write", "execute"]},
    ]

    permissions = offline_host.get_permissions()

    # Should be the union of all permissions
    assert set(permissions) == {"read", "write", "execute"}


def test_get_state_returns_stopped_when_snapshots_exist(offline_host: OfflineHost, mock_provider):
    """Test that get_state returns STOPPED when snapshots exist."""
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("snap1"),
            created_at=datetime.now(timezone.utc),
        )
    ]

    state = offline_host.get_state()
    assert state == HostState.STOPPED


def test_get_state_returns_destroyed_when_no_snapshots(offline_host: OfflineHost, mock_provider):
    """Test that get_state returns DESTROYED when no snapshots exist."""
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = []

    state = offline_host.get_state()
    assert state == HostState.DESTROYED


def test_get_state_returns_stopped_when_provider_does_not_support_snapshots(
    offline_host: OfflineHost, mock_provider
):
    """Test that get_state returns STOPPED when provider doesn't support snapshots."""
    mock_provider.supports_snapshots = False

    state = offline_host.get_state()
    assert state == HostState.STOPPED


def test_get_state_returns_stopped_when_snapshot_check_fails(offline_host: OfflineHost, mock_provider):
    """Test that get_state returns STOPPED when snapshot check raises an exception."""
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.side_effect = OSError("Connection failed")

    state = offline_host.get_state()
    assert state == HostState.STOPPED


def test_is_online_defaults_to_false(mock_provider, mock_mngr_ctx):
    """Test that is_online defaults to False."""
    host = OfflineHost(
        id=HostId.generate(),
        certified_host_data=CertifiedHostData(),
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )
    assert host.is_online is False
