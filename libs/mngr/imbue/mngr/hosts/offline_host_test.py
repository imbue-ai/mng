"""Unit tests for OfflineHost implementation."""

from unittest.mock import create_autospec

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.offline_host import OfflineHost
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import SnapshotRecord
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
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        idle_mode=IdleMode.SSH,
        idle_timeout_seconds=3600,
        activity_sources=(ActivitySource.SSH, ActivitySource.AGENT),
        image="test-image:latest",
        plugin={"my_plugin": {"key": "value"}},
    )
    return OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
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


def test_get_all_certified_data_returns_stored_data(offline_host: OfflineHost):
    """Test that get_all_certified_data returns the certified host data."""
    data = offline_host.get_certified_data()

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


def test_get_snapshots_uses_certified_data(mock_provider, mock_mngr_ctx):
    """Test that get_snapshots returns data from certified_host_data.snapshots (avoids provider call)."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        snapshots=[
            SnapshotRecord(id="snap-test-1", name="snap1", created_at="2026-01-15T10:30:00+00:00"),
            SnapshotRecord(id="snap-test-2", name="snap2", created_at="2026-01-16T12:00:00+00:00"),
        ],
    )
    host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    snapshots = host.get_snapshots()

    # Should return snapshots sorted by created_at descending (most recent first)
    assert len(snapshots) == 2
    assert snapshots[0].id == SnapshotId("snap-test-2")
    assert snapshots[0].name == SnapshotName("snap2")
    assert snapshots[0].recency_idx == 0
    assert snapshots[1].id == SnapshotId("snap-test-1")
    assert snapshots[1].name == SnapshotName("snap1")
    assert snapshots[1].recency_idx == 1
    # Should NOT call provider
    mock_provider.list_snapshots.assert_not_called()


def test_get_image_returns_image_from_certified_data(offline_host: OfflineHost):
    """Test that get_image returns the image from certified data."""
    image = offline_host.get_image()
    assert image == "test-image:latest"


def test_get_tags_uses_certified_data(mock_provider, mock_mngr_ctx):
    """Test that get_tags returns data from certified_host_data.user_tags (avoids provider call)."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        user_tags={"env": "production", "team": "infra"},
    )
    host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    tags = host.get_tags()

    assert tags == {"env": "production", "team": "infra"}
    # Should NOT call provider
    mock_provider.get_host_tags.assert_not_called()


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
    mock_provider.list_persisted_agent_data_for_host.return_value = [{"invalid_key": "missing id and name"}]

    refs = offline_host.get_agent_references()
    assert refs == []


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


def test_get_state_returns_crashed_when_no_stop_reason(mock_provider, mock_mngr_ctx):
    """Test that get_state returns CRASHED when snapshots exist but no stop_reason is set."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        snapshots=[
            SnapshotRecord(id="snap-test-2", name="snap1", created_at="2026-01-15T10:30:00+00:00"),
        ],
    )
    mock_provider.supports_snapshots = True
    host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    state = host.get_state()
    # No stop_reason means host didn't shut down cleanly
    assert state == HostState.CRASHED


def test_get_state_returns_destroyed_when_no_snapshots(offline_host: OfflineHost, mock_provider):
    """Test that get_state returns DESTROYED when no snapshots exist."""
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = []

    state = offline_host.get_state()
    assert state == HostState.DESTROYED


def test_get_state_returns_crashed_when_provider_does_not_support_snapshots_and_no_stop_reason(
    offline_host: OfflineHost, mock_provider
):
    """Test that get_state returns CRASHED when provider doesn't support snapshots and no stop_reason."""
    mock_provider.supports_snapshots = False

    state = offline_host.get_state()
    # No stop_reason means host didn't shut down cleanly
    assert state == HostState.CRASHED


def test_get_state_returns_failed_when_certified_data_has_failed_state(mock_provider, mock_mngr_ctx):
    """Test that get_state returns FAILED when certified data indicates failure."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        state=HostState.FAILED.value,
        failure_reason="Docker build failed",
        build_log="Step 1/5: RUN apt-get update\nERROR: apt-get failed",
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    state = failed_host.get_state()
    assert state == HostState.FAILED


def test_get_failure_reason_returns_reason_when_present(mock_provider, mock_mngr_ctx):
    """Test that get_failure_reason returns the failure reason from certified data."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        state=HostState.FAILED.value,
        failure_reason="Modal sandbox creation failed",
        build_log="Build log contents",
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    reason = failed_host.get_failure_reason()
    assert reason == "Modal sandbox creation failed"


def test_get_failure_reason_returns_none_for_successful_host(offline_host: OfflineHost):
    """Test that get_failure_reason returns None for hosts that did not fail."""
    reason = offline_host.get_failure_reason()
    assert reason is None


def test_get_build_log_returns_log_when_present(mock_provider, mock_mngr_ctx):
    """Test that get_build_log returns the build log from certified data."""
    host_id = HostId.generate()
    build_log_content = "Step 1/5: FROM ubuntu:22.04\nStep 2/5: RUN apt-get update\nERROR: network error"
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        state=HostState.FAILED.value,
        failure_reason="Build failed",
        build_log=build_log_content,
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    log = failed_host.get_build_log()
    assert log == build_log_content


def test_get_build_log_returns_none_for_successful_host(offline_host: OfflineHost):
    """Test that get_build_log returns None for hosts that did not fail."""
    log = offline_host.get_build_log()
    assert log is None


def test_failed_state_takes_precedence_over_snapshot_check(mock_provider, mock_mngr_ctx):
    """Test that FAILED state is returned even when snapshots exist."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        state=HostState.FAILED.value,
        failure_reason="Build failed",
        snapshots=[
            SnapshotRecord(id="snap-test", name="should-not-matter", created_at="2026-01-15T10:30:00+00:00"),
        ],
    )
    mock_provider.supports_snapshots = True
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    state = failed_host.get_state()
    # FAILED state takes precedence over snapshots
    assert state == HostState.FAILED


@pytest.mark.parametrize(
    "stop_reason,expected_state",
    [
        (HostState.PAUSED.value, HostState.PAUSED),
        (HostState.STOPPED.value, HostState.STOPPED),
        (None, HostState.CRASHED),
    ],
    ids=["paused", "stopped", "crashed_no_stop_reason"],
)
def test_get_state_based_on_stop_reason(mock_provider, mock_mngr_ctx, stop_reason, expected_state):
    """Test that get_state returns the correct state based on stop_reason."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        stop_reason=stop_reason,
        snapshots=[
            SnapshotRecord(id="snap-test", name="snapshot", created_at="2026-01-15T10:30:00+00:00"),
        ],
    )
    mock_provider.supports_snapshots = True
    host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=mock_provider,
        mngr_ctx=mock_mngr_ctx,
    )

    state = host.get_state()
    assert state == expected_state
