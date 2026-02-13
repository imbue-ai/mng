import os
import time
from pathlib import Path

from imbue.mngr.api.enforce import EnforceAction
from imbue.mngr.api.enforce import EnforceResult
from imbue.mngr.api.enforce import enforce
from imbue.mngr.hosts.host import Host
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
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


# =============================================================================
# Tests for get_idle_seconds activity_sources filtering
# =============================================================================


def _write_activity_file(host_dir: Path, source: ActivitySource, age_seconds: float) -> None:
    """Write a host-level activity file with the given age (seconds in the past)."""
    activity_dir = host_dir / "activity"
    activity_dir.mkdir(parents=True, exist_ok=True)
    activity_file = activity_dir / source.value.lower()
    activity_file.write_text("{}")
    desired_mtime = time.time() - age_seconds
    os.utime(activity_file, (desired_mtime, desired_mtime))


def test_get_idle_seconds_respects_activity_sources(local_provider: LocalProviderInstance) -> None:
    """get_idle_seconds should only check the specified activity_sources.

    Uses host-level sources (BOOT, SSH, USER) which are stored directly in
    the host_dir/activity/ directory and don't require agent data.json setup.
    """
    host = local_provider.create_host(HostName("test-idle"))
    assert isinstance(host, Host)

    # Write BOOT activity 100s ago and SSH activity 2s ago
    _write_activity_file(host.host_dir, ActivitySource.BOOT, age_seconds=100)
    _write_activity_file(host.host_dir, ActivitySource.SSH, age_seconds=2)

    # Checking only BOOT: idle_seconds should be ~100
    idle_boot = host.get_idle_seconds(activity_sources=(ActivitySource.BOOT,))
    assert idle_boot >= 95

    # Checking only SSH: idle_seconds should be ~2
    idle_ssh = host.get_idle_seconds(activity_sources=(ActivitySource.SSH,))
    assert idle_ssh < 10

    # Checking both: idle_seconds should be ~2 (most recent wins)
    idle_both = host.get_idle_seconds(activity_sources=(ActivitySource.BOOT, ActivitySource.SSH))
    assert idle_both < 10

    # Checking no sources (disabled mode): idle_seconds should be inf
    idle_none = host.get_idle_seconds(activity_sources=())
    assert idle_none == float("inf")


def test_get_idle_seconds_without_filter_checks_all_sources(local_provider: LocalProviderInstance) -> None:
    """get_idle_seconds without activity_sources checks all sources (backwards compat)."""
    host = local_provider.create_host(HostName("test-idle-all"))
    assert isinstance(host, Host)

    # Write USER activity 3s ago (the host also has BOOT from create_host)
    _write_activity_file(host.host_dir, ActivitySource.USER, age_seconds=3)

    # Without filtering, should find USER (most recent) and return ~3s
    idle_all = host.get_idle_seconds()
    assert idle_all < 10

    # Empty sources returns inf (no sources to check)
    idle_empty = host.get_idle_seconds(activity_sources=())
    assert idle_empty == float("inf")
