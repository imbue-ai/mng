"""Unit tests for enforce API functions."""

from imbue.mngr.api.enforce import EnforceAction
from imbue.mngr.api.enforce import EnforceResult
from imbue.mngr.api.enforce import enforce
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance


def test_enforce_action_model_can_be_created() -> None:
    """EnforceAction should be constructible with all required fields."""
    action = EnforceAction(
        host_id=HostId.generate(),
        host_name="test-host",
        provider_name=ProviderInstanceName("local"),
        host_state=HostState.RUNNING,
        action="stop_host",
        reason="Idle timeout exceeded",
        is_dry_run=False,
    )
    assert action.action == "stop_host"
    assert action.host_state == HostState.RUNNING


def test_enforce_result_defaults() -> None:
    """EnforceResult should have sensible defaults."""
    result = EnforceResult()
    assert result.actions == []
    assert result.hosts_checked == 0
    assert result.idle_violations == 0
    assert result.timeout_violations == 0
    assert result.errors == []


def test_enforce_skips_local_hosts_for_idle_check(local_provider: LocalProviderInstance) -> None:
    """enforce should skip local hosts when checking idle timeouts."""
    result = enforce(
        providers=[local_provider],
        is_check_idle=True,
        is_check_timeouts=False,
        building_timeout_seconds=1800,
        starting_timeout_seconds=900,
        stopping_timeout_seconds=600,
        is_dry_run=False,
        error_behavior=ErrorBehavior.ABORT,
    )

    # Local host should be skipped (not stopped)
    assert len(result.actions) == 0
    assert result.idle_violations == 0
    # The local host should still be counted as checked
    assert result.hosts_checked >= 1


def test_enforce_with_no_providers() -> None:
    """enforce should return empty result when no providers are given."""
    result = enforce(
        providers=[],
        is_check_idle=True,
        is_check_timeouts=True,
        building_timeout_seconds=1800,
        starting_timeout_seconds=900,
        stopping_timeout_seconds=600,
        is_dry_run=False,
        error_behavior=ErrorBehavior.ABORT,
    )

    assert result.hosts_checked == 0
    assert len(result.actions) == 0
    assert len(result.errors) == 0


def test_enforce_dry_run_does_not_take_action(local_provider: LocalProviderInstance) -> None:
    """enforce in dry-run mode should not modify any hosts."""
    result = enforce(
        providers=[local_provider],
        is_check_idle=True,
        is_check_timeouts=True,
        building_timeout_seconds=1800,
        starting_timeout_seconds=900,
        stopping_timeout_seconds=600,
        is_dry_run=True,
        error_behavior=ErrorBehavior.ABORT,
    )

    # With local provider, no actions should be taken (local hosts are skipped)
    assert len(result.actions) == 0
    assert len(result.errors) == 0


def test_enforce_with_only_timeout_checks(local_provider: LocalProviderInstance) -> None:
    """enforce with only timeout checks enabled should skip idle check."""
    result = enforce(
        providers=[local_provider],
        is_check_idle=False,
        is_check_timeouts=True,
        building_timeout_seconds=1800,
        starting_timeout_seconds=900,
        stopping_timeout_seconds=600,
        is_dry_run=True,
        error_behavior=ErrorBehavior.ABORT,
    )

    # Local host is RUNNING so timeout checks don't apply
    assert result.idle_violations == 0
    assert result.timeout_violations == 0


def test_enforce_action_serializes_to_json() -> None:
    """EnforceAction should serialize to JSON correctly."""
    action = EnforceAction(
        host_id=HostId.generate(),
        host_name="test-host",
        provider_name=ProviderInstanceName("docker"),
        host_state=HostState.RUNNING,
        action="stop_host",
        reason="Idle for 3700s, exceeding timeout of 3600s",
        is_dry_run=True,
    )
    dumped = action.model_dump(mode="json")
    assert dumped["action"] == "stop_host"
    assert dumped["host_state"] == "RUNNING"
    assert dumped["is_dry_run"] is True
    assert dumped["reason"] == "Idle for 3700s, exceeding timeout of 3600s"
