from datetime import datetime
from datetime import timezone
from pathlib import Path

from imbue.mngr.api.list import AgentInfo
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName


def make_test_agent_info(
    name: str = "test-agent",
    state: AgentLifecycleState = AgentLifecycleState.RUNNING,
    create_time: datetime | None = None,
    snapshots: list[SnapshotInfo] | None = None,
) -> AgentInfo:
    """Create a real AgentInfo for testing.

    Shared helper used across test files to avoid duplicating AgentInfo
    construction logic. Accepts optional overrides for commonly varied fields.
    """
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        snapshots=snapshots or [],
        state=HostState.RUNNING,
    )
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="generic",
        command=CommandString("sleep 100"),
        work_dir=Path("/tmp/test"),
        create_time=create_time or datetime.now(timezone.utc),
        start_on_boot=False,
        state=state,
        host=host_info,
    )
