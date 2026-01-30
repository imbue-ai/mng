"""Unit tests for gc API functions."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imbue.mngr.api.data_types import GcResult
from imbue.mngr.api.gc import _apply_cel_filters
from imbue.mngr.api.gc import _get_orphaned_work_dirs
from imbue.mngr.api.gc import _resource_to_cel_context
from imbue.mngr.api.gc import gc_machines
from imbue.mngr.api.gc import gc_snapshots
from imbue.mngr.api.gc import gc_volumes
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.data_types import BuildCacheInfo
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.data_types import LogFileInfo
from imbue.mngr.interfaces.data_types import SizeBytes
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.cel_utils import compile_cel_filters

# =============================================================================
# Basic _resource_to_cel_context tests
# =============================================================================


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
        id=SnapshotId.generate(),
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


# =============================================================================
# CEL filter tests
# =============================================================================


def test_compile_and_apply_cel_filters_include() -> None:
    """Test CEL filter compilation and application with include filters."""
    snapshot = SnapshotInfo(
        id=SnapshotId.generate(),
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
        id=SnapshotId.generate(),
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
        id=SnapshotId.generate(),
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
        id=SnapshotId.generate(),
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
        id=SnapshotId.generate(),
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
        id=SnapshotId.generate(),
        name=SnapshotName("small-snapshot"),
        created_at=datetime.now(timezone.utc),
        size_bytes=100,
    )

    include_filters, exclude_filters = compile_cel_filters(
        include_filters=["size > 1000000000"],
        exclude_filters=[],
    )

    assert not _apply_cel_filters(snapshot, include_filters, exclude_filters)


# =============================================================================
# gc_machines tests
# =============================================================================


def test_gc_machines_skips_local_hosts(local_provider: LocalProviderInstance) -> None:
    """Test that gc_machines skips local hosts even when they have no agents."""
    result = GcResult()

    gc_machines(
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


# =============================================================================
# Additional _resource_to_cel_context age calculation tests
# =============================================================================


def test_resource_to_cel_context_age_from_created_at_takes_precedence(tmp_path: Path) -> None:
    """Test that created_at takes precedence over filesystem stat for age calculation."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("content")

    created_30_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    cache_info = BuildCacheInfo(
        path=test_file,
        size_bytes=SizeBytes(100),
        created_at=created_30_days_ago,
    )

    context = _resource_to_cel_context(cache_info)

    expected_age = 30 * 24 * 3600
    assert expected_age - 60 < context["age"] < expected_age + 60


def test_resource_to_cel_context_age_when_path_does_not_exist() -> None:
    """Test that age is calculated from created_at when path doesn't exist."""
    non_existent_path = Path("/non/existent/path/that/does/not/exist")
    created_time = datetime.now(timezone.utc) - timedelta(hours=2)

    cache_info = BuildCacheInfo(
        path=non_existent_path,
        size_bytes=SizeBytes(50),
        created_at=created_time,
    )

    context = _resource_to_cel_context(cache_info)

    assert 2 * 3600 - 10 < context["age"] < 2 * 3600 + 10


def test_resource_to_cel_context_raises_for_non_model() -> None:
    """Test that an error is raised for resources without model_dump."""

    class NonPydanticResource:
        pass

    with pytest.raises(MngrError, match="Cannot convert resource type"):
        _resource_to_cel_context(NonPydanticResource())


# =============================================================================
# _get_orphaned_work_dirs tests
# =============================================================================


def _create_mock_host_for_orphan_test(
    host_id: HostId,
    generated_work_dirs: tuple[str, ...],
    active_work_dirs: list[str],
    du_success: bool = True,
    du_output: str = "1024",
    stat_success: bool = True,
    stat_output: str = "1700000000",
) -> MagicMock:
    """Create a mock host with configurable behavior for orphan tests."""
    mock_host = MagicMock()
    mock_host.id = host_id
    mock_host.is_local = False

    mock_certified_data = CertifiedHostData(generated_work_dirs=generated_work_dirs)
    mock_host.get_all_certified_data.return_value = mock_certified_data

    mock_agents = []
    for work_dir in active_work_dirs:
        mock_agent = MagicMock()
        mock_agent.work_dir = Path(work_dir)
        mock_agents.append(mock_agent)
    mock_host.get_agents.return_value = mock_agents

    def mock_execute_command(cmd: str) -> CommandResult:
        if cmd.startswith("du "):
            return CommandResult(
                stdout=du_output if du_success else "",
                stderr="" if du_success else "error",
                success=du_success,
            )
        elif cmd.startswith("stat "):
            return CommandResult(
                stdout=stat_output if stat_success else "",
                stderr="" if stat_success else "error",
                success=stat_success,
            )
        else:
            return CommandResult(stdout="", stderr="", success=True)

    mock_host.execute_command.side_effect = mock_execute_command
    return mock_host


def test_get_orphaned_work_dirs_identifies_orphans() -> None:
    """Test that orphaned work dirs are correctly identified."""
    host_id = HostId.generate()
    provider_name = ProviderInstanceName("test-provider")

    mock_host = _create_mock_host_for_orphan_test(
        host_id=host_id,
        generated_work_dirs=("/work/dir1", "/work/dir2", "/work/dir3"),
        active_work_dirs=["/work/dir1"],
    )

    orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

    orphaned_paths = {str(d.path) for d in orphaned}
    assert orphaned_paths == {"/work/dir2", "/work/dir3"}


def test_get_orphaned_work_dirs_none_when_all_active() -> None:
    """Test that no orphans are returned when all dirs are active."""
    host_id = HostId.generate()
    provider_name = ProviderInstanceName("test-provider")

    mock_host = _create_mock_host_for_orphan_test(
        host_id=host_id,
        generated_work_dirs=("/work/dir1", "/work/dir2"),
        active_work_dirs=["/work/dir1", "/work/dir2"],
    )

    orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

    assert len(orphaned) == 0


def test_get_orphaned_work_dirs_size_parsing() -> None:
    """Test that size is correctly parsed from du command output."""
    host_id = HostId.generate()
    provider_name = ProviderInstanceName("test-provider")

    mock_host = _create_mock_host_for_orphan_test(
        host_id=host_id,
        generated_work_dirs=("/work/orphan",),
        active_work_dirs=[],
        du_success=True,
        du_output="5678",
    )

    orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

    assert len(orphaned) == 1
    assert orphaned[0].size_bytes == 5678


def test_get_orphaned_work_dirs_size_defaults_on_failure() -> None:
    """Test that size defaults to 0 when du command fails."""
    host_id = HostId.generate()
    provider_name = ProviderInstanceName("test-provider")

    mock_host = _create_mock_host_for_orphan_test(
        host_id=host_id,
        generated_work_dirs=("/work/orphan",),
        active_work_dirs=[],
        du_success=False,
    )

    orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

    assert len(orphaned) == 1
    assert orphaned[0].size_bytes == 0


def test_get_orphaned_work_dirs_timestamp_parsing() -> None:
    """Test that created_at is correctly parsed from stat command output."""
    host_id = HostId.generate()
    provider_name = ProviderInstanceName("test-provider")

    timestamp = 1700000000
    mock_host = _create_mock_host_for_orphan_test(
        host_id=host_id,
        generated_work_dirs=("/work/orphan",),
        active_work_dirs=[],
        stat_success=True,
        stat_output=str(timestamp),
    )

    orphaned = _get_orphaned_work_dirs(host=mock_host, provider_name=provider_name)

    assert len(orphaned) == 1
    expected_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    assert orphaned[0].created_at == expected_dt


# =============================================================================
# gc_snapshots tests
# =============================================================================


def _create_mock_provider_for_snapshots(
    supports_snapshots: bool,
    hosts: list[MagicMock],
) -> MagicMock:
    """Create a mock provider with configurable snapshot support."""
    mock_provider = MagicMock()
    mock_provider.name = ProviderInstanceName("test-provider")
    mock_provider.supports_snapshots = supports_snapshots
    mock_provider.list_hosts.return_value = hosts
    return mock_provider


def test_gc_snapshots_recency_index() -> None:
    """Test that recency_idx is correctly assigned based on creation time."""
    mock_host = MagicMock()
    mock_host.id = HostId.generate()

    now = datetime.now(timezone.utc)
    snapshots = [
        SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("oldest"),
            created_at=now - timedelta(days=10),
            size_bytes=100,
        ),
        SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("newest"),
            created_at=now - timedelta(days=1),
            size_bytes=200,
        ),
        SnapshotInfo(
            id=SnapshotId.generate(),
            name=SnapshotName("middle"),
            created_at=now - timedelta(days=5),
            size_bytes=150,
        ),
    ]

    mock_provider = _create_mock_provider_for_snapshots(
        supports_snapshots=True,
        hosts=[mock_host],
    )
    mock_provider.list_snapshots.return_value = snapshots

    result = GcResult()
    gc_snapshots(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.snapshots_destroyed) == 3
    destroyed_by_name = {s.name: s for s in result.snapshots_destroyed}

    assert destroyed_by_name["newest"].recency_idx == 0
    assert destroyed_by_name["middle"].recency_idx == 1
    assert destroyed_by_name["oldest"].recency_idx == 2


def test_gc_snapshots_skips_unsupported_provider() -> None:
    """Test that providers without snapshot support are skipped."""
    mock_provider = _create_mock_provider_for_snapshots(
        supports_snapshots=False,
        hosts=[],
    )

    result = GcResult()
    gc_snapshots(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    mock_provider.list_hosts.assert_not_called()
    assert len(result.snapshots_destroyed) == 0


def test_gc_snapshots_dry_run() -> None:
    """Test that dry_run=True does not actually delete snapshots."""
    mock_host = MagicMock()
    mock_host.id = HostId.generate()

    snapshot = SnapshotInfo(
        id=SnapshotId.generate(),
        name=SnapshotName("test"),
        created_at=datetime.now(timezone.utc),
        size_bytes=100,
    )

    mock_provider = _create_mock_provider_for_snapshots(
        supports_snapshots=True,
        hosts=[mock_host],
    )
    mock_provider.list_snapshots.return_value = [snapshot]

    result = GcResult()
    gc_snapshots(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.snapshots_destroyed) == 1
    mock_provider.delete_snapshot.assert_not_called()


# =============================================================================
# gc_volumes tests
# =============================================================================


def _create_mock_provider_for_volumes(
    supports_volumes: bool,
    all_volumes: list[VolumeInfo],
    active_hosts: list[MagicMock],
) -> MagicMock:
    """Create a mock provider with configurable volume support."""
    mock_provider = MagicMock()
    mock_provider.name = ProviderInstanceName("test-provider")
    mock_provider.supports_volumes = supports_volumes
    mock_provider.list_volumes.return_value = all_volumes
    mock_provider.list_hosts.return_value = active_hosts
    return mock_provider


def test_gc_volumes_identifies_orphans() -> None:
    """Test that volumes with host_id not matching active hosts are orphaned."""
    active_host_id = HostId.generate()
    inactive_host_id = HostId.generate()

    mock_host = MagicMock()
    mock_host.id = active_host_id

    volumes = [
        VolumeInfo(
            volume_id=VolumeId.generate(),
            name="active-volume",
            size_bytes=1000,
            created_at=datetime.now(timezone.utc),
            host_id=active_host_id,
        ),
        VolumeInfo(
            volume_id=VolumeId.generate(),
            name="orphan-volume",
            size_bytes=2000,
            created_at=datetime.now(timezone.utc),
            host_id=inactive_host_id,
        ),
        VolumeInfo(
            volume_id=VolumeId.generate(),
            name="unattached-volume",
            size_bytes=3000,
            created_at=datetime.now(timezone.utc),
            host_id=None,
        ),
    ]

    mock_provider = _create_mock_provider_for_volumes(
        supports_volumes=True,
        all_volumes=volumes,
        active_hosts=[mock_host],
    )

    result = GcResult()
    gc_volumes(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    destroyed_names = {v.name for v in result.volumes_destroyed}
    assert destroyed_names == {"orphan-volume", "unattached-volume"}


def test_gc_volumes_none_when_all_attached() -> None:
    """Test that no orphans are found when all volumes are attached to active hosts."""
    host_id = HostId.generate()

    mock_host = MagicMock()
    mock_host.id = host_id

    volumes = [
        VolumeInfo(
            volume_id=VolumeId.generate(),
            name="attached-volume",
            size_bytes=1000,
            created_at=datetime.now(timezone.utc),
            host_id=host_id,
        ),
    ]

    mock_provider = _create_mock_provider_for_volumes(
        supports_volumes=True,
        all_volumes=volumes,
        active_hosts=[mock_host],
    )

    result = GcResult()
    gc_volumes(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.volumes_destroyed) == 0


def test_gc_volumes_skips_unsupported_provider() -> None:
    """Test that providers without volume support are skipped."""
    mock_provider = _create_mock_provider_for_volumes(
        supports_volumes=False,
        all_volumes=[],
        active_hosts=[],
    )

    result = GcResult()
    gc_volumes(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    mock_provider.list_volumes.assert_not_called()
    assert len(result.volumes_destroyed) == 0


# =============================================================================
# Additional gc_machines tests
# =============================================================================


def _create_mock_provider_for_machines(hosts: list[MagicMock]) -> MagicMock:
    """Create a mock provider with the given hosts."""
    mock_provider = MagicMock()
    mock_provider.name = ProviderInstanceName("test-provider")
    mock_provider.list_hosts.return_value = hosts
    return mock_provider


def _create_mock_host_for_machine_test(
    host_id: HostId,
    is_local: bool = False,
    agent_count: int = 0,
) -> MagicMock:
    """Create a mock host with configurable agent count."""
    mock_host = MagicMock()
    mock_host.id = host_id
    mock_host.is_local = is_local
    mock_agents = [MagicMock() for _ in range(agent_count)]
    mock_host.get_agents.return_value = mock_agents
    return mock_host


def test_gc_machines_host_with_agents_not_collected() -> None:
    """Test that hosts with agents are NOT garbage collected."""
    host_id = HostId.generate()
    mock_host = _create_mock_host_for_machine_test(
        host_id=host_id,
        is_local=False,
        agent_count=1,
    )

    mock_provider = _create_mock_provider_for_machines(hosts=[mock_host])

    result = GcResult()
    gc_machines(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=False,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.machines_destroyed) == 0
    mock_provider.destroy_host.assert_not_called()


def test_gc_machines_host_without_agents_collected() -> None:
    """Test that hosts without agents ARE garbage collected."""
    host_id = HostId.generate()
    mock_host = _create_mock_host_for_machine_test(
        host_id=host_id,
        is_local=False,
        agent_count=0,
    )

    mock_provider = _create_mock_provider_for_machines(hosts=[mock_host])

    result = GcResult()
    gc_machines(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.machines_destroyed) == 1
    assert result.machines_destroyed[0].id == host_id


def test_gc_machines_multiple_hosts_mixed() -> None:
    """Test gc with multiple hosts having different agent counts."""
    host_with_agents = _create_mock_host_for_machine_test(
        host_id=HostId.generate(),
        is_local=False,
        agent_count=2,
    )
    host_without_agents = _create_mock_host_for_machine_test(
        host_id=HostId.generate(),
        is_local=False,
        agent_count=0,
    )
    local_host = _create_mock_host_for_machine_test(
        host_id=HostId.generate(),
        is_local=True,
        agent_count=0,
    )

    mock_provider = _create_mock_provider_for_machines(hosts=[host_with_agents, host_without_agents, local_host])

    result = GcResult()
    gc_machines(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.machines_destroyed) == 1
    assert result.machines_destroyed[0].id == host_without_agents.id


def test_gc_machines_dry_run() -> None:
    """Test that dry_run=True does not actually destroy hosts."""
    host_id = HostId.generate()
    mock_host = _create_mock_host_for_machine_test(
        host_id=host_id,
        is_local=False,
        agent_count=0,
    )

    mock_provider = _create_mock_provider_for_machines(hosts=[mock_host])

    result = GcResult()
    gc_machines(
        providers=[mock_provider],
        include_filters=(),
        exclude_filters=(),
        dry_run=True,
        error_behavior=ErrorBehavior.CONTINUE,
        result=result,
    )

    assert len(result.machines_destroyed) == 1
    mock_provider.destroy_host.assert_not_called()
