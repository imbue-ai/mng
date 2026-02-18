"""Unit tests for gc API functions."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest

from imbue.mngr.api.data_types import GcResult
from imbue.mngr.api.gc import _apply_cel_filters
from imbue.mngr.api.gc import _resource_to_cel_context
from imbue.mngr.api.gc import gc_machines
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.offline_host import OfflineHost
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import LogFileInfo
from imbue.mngr.interfaces.data_types import SizeBytes
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.providers.mock_provider_test import MockProviderInstance
from imbue.mngr.providers.mock_provider_test import make_offline_host
from imbue.mngr.utils.cel_utils import compile_cel_filters


def test_resource_to_cel_context_for_path(tmp_path: Path) -> None:
    """Test converting LogFileInfo objects to CEL context."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    created_at = datetime.fromtimestamp(test_file.stat().st_ctime, tz=timezone.utc)
    log_file_info = LogFileInfo(path=test_file, size_bytes=SizeBytes(len("test content")), created_at=created_at)
    context = _resource_to_cel_context(log_file_info)

    assert context["type"] == "logfile"
    assert context["name"] == "test.txt"
    assert context["path"] == str(test_file)
    assert context["size"] == len("test content")
    assert "age" in context
    assert isinstance(context["age"], (int, float))


def test_resource_to_cel_context_for_snapshot() -> None:
    """Test converting SnapshotInfo to CEL context."""
    created_time = datetime.now(timezone.utc) - timedelta(days=7)
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("test-snapshot"),
        created_at=created_time,
        size_bytes=1000000,
    )

    context = _resource_to_cel_context(snapshot)

    assert context["type"] == "snapshot"
    assert context["name"] == "test-snapshot"
    assert context["size"] == 1000000
    assert context["size_bytes"] == 1000000
    assert "age" in context
    assert 7 * 24 * 3600 - 10 < context["age"] < 7 * 24 * 3600 + 10


def test_resource_to_cel_context_for_volume() -> None:
    """Test converting VolumeInfo to CEL context."""
    created_time = datetime.now(timezone.utc) - timedelta(hours=2)
    volume = VolumeInfo(
        volume_id=VolumeId.generate(),
        name="test-volume",
        size_bytes=500000000,
        created_at=created_time,
        host_id=HostId.generate(),
    )

    context = _resource_to_cel_context(volume)

    assert context["type"] == "volume"
    assert context["name"] == "test-volume"
    assert context["size"] == 500000000
    assert context["size_bytes"] == 500000000
    assert "age" in context
    assert 2 * 3600 - 10 < context["age"] < 2 * 3600 + 10


def test_compile_and_apply_cel_filters_include() -> None:
    """Test CEL filter compilation and application with include filters."""
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("large-snapshot"),
        created_at=datetime.now(timezone.utc) - timedelta(days=10),
        size_bytes=2000000000,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=["size > 1000000000"],
        exclude_filters=[],
    )

    assert _apply_cel_filters(snapshot, include_filters, exclude_filters)


def test_compile_and_apply_cel_filters_exclude() -> None:
    """Test CEL filter compilation and application with exclude filters."""
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("old-snapshot"),
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
        size_bytes=500000,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=[],
        exclude_filters=["age > 2592000"],
    )

    assert not _apply_cel_filters(snapshot, include_filters, exclude_filters)


def test_compile_and_apply_cel_filters_name_matching() -> None:
    """Test CEL filter with name pattern matching."""
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("temp-snapshot-123"),
        created_at=datetime.now(timezone.utc),
        size_bytes=100000,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=[],
        exclude_filters=["name.startsWith('temp')"],
    )

    assert not _apply_cel_filters(snapshot, include_filters, exclude_filters)


def test_compile_and_apply_cel_filters_multiple() -> None:
    """Test CEL filter with multiple conditions."""
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("prod-snapshot"),
        created_at=datetime.now(timezone.utc) - timedelta(days=15),
        size_bytes=3000000000,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=["size > 1000000000", "age > 604800"],
        exclude_filters=["name.startsWith('temp')"],
    )

    assert _apply_cel_filters(snapshot, include_filters, exclude_filters)


def test_compile_and_apply_cel_filters_empty_filters() -> None:
    """Test CEL filter with no filters returns True."""
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("any-snapshot"),
        created_at=datetime.now(timezone.utc),
        size_bytes=1000,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=[],
        exclude_filters=[],
    )

    assert _apply_cel_filters(snapshot, include_filters, exclude_filters)


def test_compile_and_apply_cel_filters_include_not_matching() -> None:
    """Test CEL filter with include that doesn't match returns False."""
    snapshot = SnapshotInfo(
        id=SnapshotId("snap-test"),
        name=SnapshotName("small-snapshot"),
        created_at=datetime.now(timezone.utc),
        size_bytes=100,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=["size > 1000000000"],
        exclude_filters=[],
    )

    assert not _apply_cel_filters(snapshot, include_filters, exclude_filters)


def test_gc_machines_skips_local_hosts(local_provider: LocalProviderInstance, temp_mngr_ctx: MngrContext) -> None:
    """Test that gc_machines skips local hosts even when they have no agents."""
    result = GcResult()

    gc_machines(
        mngr_ctx=temp_mngr_ctx,
        providers=[local_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=False,
        error_behavior=ErrorBehavior.ABORT,
        result=result,
    )

    # Local host should be skipped, not destroyed
    assert len(result.machines_destroyed) == 0
    assert len(result.errors) == 0


# =========================================================================
# gc_machines offline host deletion tests
# =========================================================================


@pytest.fixture
def gc_mock_provider(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> MockProviderInstance:
    """Create a MockProviderInstance for gc_machines tests."""
    return MockProviderInstance(
        name=ProviderInstanceName("test-provider"),
        host_dir=temp_host_dir,
        mngr_ctx=temp_mngr_ctx,
    )


def _make_offline_host(
    provider: MockProviderInstance,
    mngr_ctx: MngrContext,
    *,
    days_old: int = 14,
    stop_reason: str | None = HostState.STOPPED.value,
    failure_reason: str | None = None,
) -> OfflineHost:
    """Create an offline host with configurable age and state."""
    stopped_at = datetime.now(timezone.utc) - timedelta(days=days_old)
    certified_data = CertifiedHostData(
        host_id=str(HostId.generate()),
        host_name="test-host",
        stop_reason=stop_reason,
        failure_reason=failure_reason,
        created_at=stopped_at - timedelta(hours=1),
        updated_at=stopped_at,
    )
    return make_offline_host(certified_data, provider, mngr_ctx)


def _run_gc_machines(provider: MockProviderInstance, *, dry_run: bool = False) -> GcResult:
    """Run gc_machines on a single provider and return the result."""
    result = GcResult()
    gc_machines(
        mngr_ctx=provider.mngr_ctx,
        providers=[provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=dry_run,
        error_behavior=ErrorBehavior.ABORT,
        result=result,
    )
    return result


def test_gc_machines_deletes_old_offline_host_with_no_agents(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Old offline hosts with no agents are deleted to prevent data accumulation."""
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx, days_old=14)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider)

    assert len(result.machines_deleted) == 1
    assert result.machines_deleted[0].id == host.id
    assert gc_mock_provider.deleted_hosts == [host.id]


def test_gc_machines_skips_recent_offline_host(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Offline hosts stopped less than the max persisted seconds ago are not deleted."""
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx, days_old=1)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider)

    assert len(result.machines_deleted) == 0
    assert gc_mock_provider.deleted_hosts == []


def _add_mock_agent(provider: MockProviderInstance) -> None:
    """Add a mock agent to the provider so hosts appear to have agents."""
    agent_id = AgentId.generate()
    provider.mock_agent_data = [{"id": str(agent_id), "name": "test-agent"}]


def test_gc_machines_deletes_old_crashed_host_with_agents(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Old offline hosts in CRASHED state are deleted even if they have agents."""
    # None stop_reason means the host CRASHED
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx, stop_reason=None)
    _add_mock_agent(gc_mock_provider)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider)

    assert len(result.machines_deleted) == 1
    assert gc_mock_provider.deleted_hosts == [host.id]


def test_gc_machines_skips_old_stopped_host_with_agents(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Old offline hosts in STOPPED state with agents are not deleted."""
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx, days_old=14)
    _add_mock_agent(gc_mock_provider)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider)

    assert len(result.machines_deleted) == 0
    assert gc_mock_provider.deleted_hosts == []


def test_gc_machines_dry_run_does_not_call_delete_host(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Dry run identifies hosts for deletion but does not actually delete them."""
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx, days_old=14)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider, dry_run=True)

    assert len(result.machines_deleted) == 1
    assert gc_mock_provider.deleted_hosts == []


def test_gc_machines_deletes_old_failed_host_with_agents(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Old offline hosts in FAILED state are deleted even if they have agents."""
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx, failure_reason="Build failed")
    _add_mock_agent(gc_mock_provider)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider)

    assert len(result.machines_deleted) == 1
    assert gc_mock_provider.deleted_hosts == [host.id]


def test_gc_machines_deletes_old_destroyed_host_with_agents(
    gc_mock_provider: MockProviderInstance, temp_mngr_ctx: MngrContext
) -> None:
    """Old offline hosts in DESTROYED state are deleted even if they have agents."""
    host = _make_offline_host(gc_mock_provider, temp_mngr_ctx)
    # Make the provider not support snapshots and not support shutdown hosts
    # so the state resolves to DESTROYED
    gc_mock_provider.mock_supports_snapshots = False
    gc_mock_provider.mock_supports_shutdown_hosts = False
    _add_mock_agent(gc_mock_provider)
    gc_mock_provider.mock_hosts = [host]

    result = _run_gc_machines(gc_mock_provider)

    assert len(result.machines_deleted) == 1
    assert gc_mock_provider.deleted_hosts == [host.id]
