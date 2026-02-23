import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mng.cli.completion import COMPLETION_CACHE_FILENAME
from imbue.mng.cli.completion_writer import write_agent_names_cache
from imbue.mng.interfaces.data_types import AgentInfo
from imbue.mng.interfaces.data_types import HostInfo
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import HostId
from imbue.mng.primitives import ProviderInstanceName

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


def test_write_agent_names_cache_writes_sorted_names(
    temp_host_dir: Path,
) -> None:
    """write_agent_names_cache should write sorted agent names to the cache file."""
    write_agent_names_cache(temp_host_dir, ["beta-agent", "alpha-agent"])

    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == ["alpha-agent", "beta-agent"]
    assert "updated_at" in cache_data


def test_write_agent_names_cache_writes_empty_list_for_no_agents(
    temp_host_dir: Path,
) -> None:
    """write_agent_names_cache should write an empty names list when no agents."""
    write_agent_names_cache(temp_host_dir, [])

    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == []


def test_write_agent_names_cache_deduplicates_names(
    temp_host_dir: Path,
) -> None:
    """write_agent_names_cache should deduplicate agent names."""
    write_agent_names_cache(temp_host_dir, ["same-name", "same-name"])

    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    cache_data = json.loads(cache_path.read_text())
    assert cache_data["names"] == ["same-name"]
