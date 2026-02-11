"""Unit tests for OfflineHost implementation."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import Field

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.offline_host import OfflineHost
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance


class _OfflineHostTestProvider(LocalProviderInstance):
    """Local provider with configurable persisted agent data for OfflineHost tests."""

    persisted_agent_data: list[dict[str, Any]] = Field(default_factory=list)

    def list_persisted_agent_data_for_host(self, host_id: HostId) -> list[dict[str, Any]]:
        return self.persisted_agent_data


def _create_provider_with_agent_data(
    temp_host_dir: Path,
    temp_mngr_ctx: MngrContext,
    agent_data: list[dict[str, Any]],
) -> _OfflineHostTestProvider:
    return _OfflineHostTestProvider(
        name=ProviderInstanceName("test-provider"),
        host_dir=temp_host_dir,
        mngr_ctx=temp_mngr_ctx,
        persisted_agent_data=agent_data,
    )


@pytest.fixture
def offline_host(local_provider: LocalProviderInstance, temp_mngr_ctx: MngrContext) -> OfflineHost:
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
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )


def test_get_activity_config_returns_config_from_certified_data(offline_host: OfflineHost) -> None:
    """Test that get_activity_config returns the correct ActivityConfig."""
    config = offline_host.get_activity_config()

    assert isinstance(config, ActivityConfig)
    assert config.idle_mode == IdleMode.SSH
    assert config.idle_timeout_seconds == 3600
    assert config.activity_sources == (ActivitySource.SSH, ActivitySource.AGENT)


def test_get_all_certified_data_returns_stored_data(offline_host: OfflineHost) -> None:
    """Test that get_all_certified_data returns the certified host data."""
    data = offline_host.get_certified_data()

    assert isinstance(data, CertifiedHostData)
    assert data.image == "test-image:latest"
    assert data.idle_mode == IdleMode.SSH


def test_get_plugin_data_returns_plugin_data_when_present(offline_host: OfflineHost) -> None:
    """Test that get_plugin_data returns data for existing plugins."""
    data = offline_host.get_plugin_data("my_plugin")
    assert data == {"key": "value"}


def test_get_plugin_data_returns_empty_dict_when_missing(offline_host: OfflineHost) -> None:
    """Test that get_plugin_data returns empty dict for non-existent plugins."""
    data = offline_host.get_plugin_data("nonexistent_plugin")
    assert data == {}


def test_get_snapshots_delegates_to_provider(offline_host: OfflineHost) -> None:
    """Test that get_snapshots delegates to the provider's list_snapshots method."""
    snapshots = offline_host.get_snapshots()
    assert snapshots == []


def test_get_image_returns_image_from_certified_data(offline_host: OfflineHost) -> None:
    """Test that get_image returns the image from certified data."""
    image = offline_host.get_image()
    assert image == "test-image:latest"


def test_get_tags_delegates_to_provider(offline_host: OfflineHost, local_provider: LocalProviderInstance) -> None:
    """Test that get_tags calls the provider's get_host_tags method."""
    local_provider.set_host_tags(offline_host, {"env": "test"})

    tags = offline_host.get_tags()
    assert tags == {"env": "test"}


def test_get_agent_references_returns_refs_from_provider(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test that get_agent_references loads agent data from provider and populates certified_data."""
    agent_id_1 = AgentId.generate()
    agent_id_2 = AgentId.generate()
    agent_data_1 = {"id": str(agent_id_1), "name": "my-agent", "type": "claude", "permissions": ["read", "write"]}
    agent_data_2 = {"id": str(agent_id_2), "name": "other-agent", "type": "codex"}

    provider = _create_provider_with_agent_data(temp_host_dir, temp_mngr_ctx, [agent_data_1, agent_data_2])

    host_id = HostId.generate()
    certified_data = CertifiedHostData(host_id=str(host_id), host_name="test-host")
    offline_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=provider,
        mngr_ctx=temp_mngr_ctx,
    )

    refs = offline_host.get_agent_references()

    assert len(refs) == 2
    assert refs[0].agent_id == agent_id_1
    assert refs[0].agent_name == AgentName("my-agent")
    assert refs[0].host_id == offline_host.id
    assert refs[0].provider_name == ProviderInstanceName("test-provider")
    assert refs[0].certified_data == agent_data_1
    assert refs[0].agent_type == "claude"
    assert refs[0].permissions == ("read", "write")

    assert refs[1].agent_id == agent_id_2
    assert refs[1].agent_name == AgentName("other-agent")
    assert refs[1].certified_data == agent_data_2
    assert refs[1].agent_type == "codex"
    assert refs[1].permissions == ()


def test_get_agent_references_returns_empty_list_on_error(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test that get_agent_references returns empty list when agent data is malformed."""
    provider = _create_provider_with_agent_data(temp_host_dir, temp_mngr_ctx, [{"invalid_key": "missing id and name"}])

    host_id = HostId.generate()
    certified_data = CertifiedHostData(host_id=str(host_id), host_name="test-host")
    offline_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=provider,
        mngr_ctx=temp_mngr_ctx,
    )

    refs = offline_host.get_agent_references()
    assert refs == []


def test_get_permissions_returns_empty_list_when_no_agents(offline_host: OfflineHost) -> None:
    """Test that get_permissions returns empty list when no agents exist."""
    permissions = offline_host.get_permissions()
    assert permissions == []


def test_get_permissions_returns_permissions_from_agents(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test that get_permissions returns union of all agent permissions from persisted data."""
    agent_id_1 = AgentId.generate()
    agent_id_2 = AgentId.generate()
    provider = _create_provider_with_agent_data(
        temp_host_dir,
        temp_mngr_ctx,
        [
            {"id": str(agent_id_1), "name": "agent-1", "permissions": ["read", "write"]},
            {"id": str(agent_id_2), "name": "agent-2", "permissions": ["write", "execute"]},
        ],
    )

    host_id = HostId.generate()
    certified_data = CertifiedHostData(host_id=str(host_id), host_name="test-host")
    offline_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=provider,
        mngr_ctx=temp_mngr_ctx,
    )

    permissions = offline_host.get_permissions()

    # Should be the union of all permissions
    assert set(permissions) == {"read", "write", "execute"}


def test_get_state_returns_crashed_when_no_stop_reason(offline_host: OfflineHost) -> None:
    """Test that get_state returns CRASHED when no stop_reason is set."""
    state = offline_host.get_state()
    # No stop_reason means host didn't shut down cleanly
    assert state == HostState.CRASHED


def test_get_state_returns_crashed_when_provider_does_not_support_snapshots_and_no_stop_reason(
    offline_host: OfflineHost,
) -> None:
    """Test that get_state returns CRASHED when provider doesn't support snapshots and no stop_reason."""
    state = offline_host.get_state()
    # No stop_reason means host didn't shut down cleanly
    assert state == HostState.CRASHED


def test_get_state_returns_failed_when_certified_data_has_failure_reason(
    local_provider: LocalProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Test that get_state returns FAILED when certified data has a failure_reason."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        failure_reason="Docker build failed",
        build_log="Step 1/5: RUN apt-get update\nERROR: apt-get failed",
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )

    state = failed_host.get_state()
    assert state == HostState.FAILED


def test_get_failure_reason_returns_reason_when_present(
    local_provider: LocalProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Test that get_failure_reason returns the failure reason from certified data."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        failure_reason="Modal sandbox creation failed",
        build_log="Build log contents",
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )

    reason = failed_host.get_failure_reason()
    assert reason == "Modal sandbox creation failed"


def test_get_failure_reason_returns_none_for_successful_host(offline_host: OfflineHost) -> None:
    """Test that get_failure_reason returns None for hosts that did not fail."""
    reason = offline_host.get_failure_reason()
    assert reason is None


def test_get_build_log_returns_log_when_present(
    local_provider: LocalProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Test that get_build_log returns the build log from certified data."""
    host_id = HostId.generate()
    build_log_content = "Step 1/5: FROM ubuntu:22.04\nStep 2/5: RUN apt-get update\nERROR: network error"
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        failure_reason="Build failed",
        build_log=build_log_content,
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )

    log = failed_host.get_build_log()
    assert log == build_log_content


def test_get_build_log_returns_none_for_successful_host(offline_host: OfflineHost) -> None:
    """Test that get_build_log returns None for hosts that did not fail."""
    log = offline_host.get_build_log()
    assert log is None


def test_get_state_returns_crashed_when_snapshot_check_fails_and_no_stop_reason(
    offline_host: OfflineHost,
) -> None:
    """Test that get_state returns CRASHED when no stop_reason is set, regardless of snapshot state."""
    state = offline_host.get_state()
    # No stop_reason means host didn't shut down cleanly
    assert state == HostState.CRASHED


def test_failure_reason_takes_precedence_over_snapshot_check(
    local_provider: LocalProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Test that FAILED is returned when failure_reason is set."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="failed-host",
        failure_reason="Build failed",
    )
    failed_host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )

    state = failed_host.get_state()
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
def test_get_state_based_on_stop_reason(
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    stop_reason: str | None,
    expected_state: HostState,
) -> None:
    """Test that get_state returns the correct state based on stop_reason."""
    host_id = HostId.generate()
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        stop_reason=stop_reason,
    )
    host = OfflineHost(
        id=host_id,
        certified_host_data=certified_data,
        provider_instance=local_provider,
        mngr_ctx=temp_mngr_ctx,
    )

    state = host.get_state()
    assert state == expected_state
