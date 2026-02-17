import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mngr.api.list import COMPLETION_CACHE_FILENAME
from imbue.mngr.api.list import ListResult
from imbue.mngr.api.list import _write_completion_cache
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.common import compute_idle_seconds
from imbue.mngr.interfaces.data_types import AgentInfo
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName

# =============================================================================
# Helpers
# =============================================================================


def _make_host_info() -> HostInfo:
    return HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
    )


def _make_agent_info(name: str, host_info: HostInfo) -> AgentInfo:
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="claude",
        command=CommandString("sleep 100"),
        work_dir=Path("/work"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        state=AgentLifecycleState.RUNNING,
        host=host_info,
    )


# =============================================================================
# Completion Cache Write Tests
# =============================================================================


def test_write_completion_cache_writes_agent_names(
    temp_host_dir: Path,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _write_completion_cache writes sorted agent names to the cache file."""
    host_info = _make_host_info()
    result = ListResult(
        agents=[
            _make_agent_info("beta-agent", host_info),
            _make_agent_info("alpha-agent", host_info),
        ]
    )

    _write_completion_cache(temp_mngr_ctx, result)

    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == ["alpha-agent", "beta-agent"]
    assert "updated_at" in cache_data


def test_write_completion_cache_writes_empty_list_for_no_agents(
    temp_host_dir: Path,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _write_completion_cache writes an empty names list when no agents."""
    result = ListResult()

    _write_completion_cache(temp_mngr_ctx, result)

    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == []


def test_write_completion_cache_deduplicates_names(
    temp_host_dir: Path,
    temp_mngr_ctx: MngrContext,
) -> None:
    """Test that _write_completion_cache deduplicates agent names."""
    host_info = _make_host_info()
    result = ListResult(
        agents=[
            _make_agent_info("same-name", host_info),
            _make_agent_info("same-name", host_info),
        ]
    )

    _write_completion_cache(temp_mngr_ctx, result)

    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == ["same-name"]


# =============================================================================
# compute_idle_seconds Tests
# =============================================================================


def testcompute_idle_seconds_returns_none_when_all_none() -> None:
    """compute_idle_seconds should return None when all activity times are None."""
    result = compute_idle_seconds(None, None, None)
    assert result is None


def testcompute_idle_seconds_uses_most_recent_activity() -> None:
    """compute_idle_seconds should compute from the most recent activity time."""
    now = datetime.now(timezone.utc)
    old_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    recent_time = now

    result = compute_idle_seconds(old_time, recent_time, None)
    assert result is not None
    # The recent_time is basically "now", so idle should be very small
    assert result < 2.0


def testcompute_idle_seconds_with_single_activity_time() -> None:
    """compute_idle_seconds should work with a single non-None activity time."""
    recent_time = datetime.now(timezone.utc)

    result = compute_idle_seconds(None, recent_time, None)
    assert result is not None
    assert result < 2.0
