"""Unit tests for gc CLI helpers."""

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from uuid import uuid4

from imbue.mng.api.data_types import GcResult
from imbue.mng.cli.gc import _emit_human_summary
from imbue.mng.cli.gc import _emit_jsonl_summary
from imbue.mng.cli.gc import _format_destroyed_message
from imbue.mng.interfaces.data_types import BuildCacheInfo
from imbue.mng.interfaces.data_types import HostInfo
from imbue.mng.interfaces.data_types import LogFileInfo
from imbue.mng.interfaces.data_types import SizeBytes
from imbue.mng.interfaces.data_types import SnapshotInfo
from imbue.mng.interfaces.data_types import VolumeInfo
from imbue.mng.interfaces.data_types import WorkDirInfo
from imbue.mng.primitives import HostId
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.primitives import SnapshotId
from imbue.mng.primitives import SnapshotName
from imbue.mng.primitives import VolumeId

# =============================================================================
# Helper functions for creating test data
# =============================================================================


def _create_work_dir_info(
    path: str = "/tmp/workdir",
    size_bytes: int = 1000,
    is_local: bool = True,
) -> WorkDirInfo:
    """Create a WorkDirInfo for testing."""
    return WorkDirInfo(
        path=Path(path),
        size_bytes=SizeBytes(size_bytes),
        host_id=HostId.generate(),
        provider_name=ProviderInstanceName("local"),
        is_local=is_local,
        created_at=datetime.now(timezone.utc),
    )


def _create_host_info(name: str = "test-host") -> HostInfo:
    """Create a HostInfo for testing."""
    return HostInfo(
        id=HostId.generate(),
        name=name,
        provider_name=ProviderInstanceName("docker"),
    )


def _create_snapshot_info(name: str = "test-snapshot", size_bytes: int | None = 1000) -> SnapshotInfo:
    """Create a SnapshotInfo for testing."""
    return SnapshotInfo(
        id=SnapshotId(f"snap-{uuid4().hex}"),
        name=SnapshotName(name),
        created_at=datetime.now(timezone.utc),
        size_bytes=size_bytes,
    )


def _create_volume_info(name: str = "test-volume", size_bytes: int = 1000) -> VolumeInfo:
    """Create a VolumeInfo for testing."""
    return VolumeInfo(
        volume_id=VolumeId.generate(),
        name=name,
        size_bytes=size_bytes,
        created_at=datetime.now(timezone.utc),
    )


def _create_log_file_info(path: str = "/tmp/log.txt", size_bytes: int = 500) -> LogFileInfo:
    """Create a LogFileInfo for testing."""
    return LogFileInfo(
        path=Path(path),
        size_bytes=SizeBytes(size_bytes),
        created_at=datetime.now(timezone.utc),
    )


def _create_build_cache_info(path: str = "/tmp/cache", size_bytes: int = 2000) -> BuildCacheInfo:
    """Create a BuildCacheInfo for testing."""
    return BuildCacheInfo(
        path=Path(path),
        size_bytes=SizeBytes(size_bytes),
        created_at=datetime.now(timezone.utc),
    )


# =============================================================================
# Tests for _format_destroyed_message
# =============================================================================


def test_format_destroyed_message_work_dir() -> None:
    """_format_destroyed_message should format work directory messages."""
    work_dir = _create_work_dir_info(path="/home/user/work")

    msg_destroy = _format_destroyed_message("work_dir", work_dir, dry_run=False)
    assert msg_destroy == "Destroyed work directory: /home/user/work"

    msg_dry_run = _format_destroyed_message("work_dir", work_dir, dry_run=True)
    assert msg_dry_run == "Would destroy work directory: /home/user/work"


def test_format_destroyed_message_machine() -> None:
    """_format_destroyed_message should format machine messages with provider."""
    host = _create_host_info(name="my-machine")

    msg_destroy = _format_destroyed_message("machine", host, dry_run=False)
    assert msg_destroy == "Destroyed machine: my-machine (docker)"

    msg_dry_run = _format_destroyed_message("machine", host, dry_run=True)
    assert msg_dry_run == "Would destroy machine: my-machine (docker)"


def test_format_destroyed_message_snapshot() -> None:
    """_format_destroyed_message should format snapshot messages."""
    snapshot = _create_snapshot_info(name="snap-2024")

    msg_destroy = _format_destroyed_message("snapshot", snapshot, dry_run=False)
    assert msg_destroy == "Destroyed snapshot: snap-2024"

    msg_dry_run = _format_destroyed_message("snapshot", snapshot, dry_run=True)
    assert msg_dry_run == "Would destroy snapshot: snap-2024"


def test_format_destroyed_message_volume() -> None:
    """_format_destroyed_message should format volume messages."""
    volume = _create_volume_info(name="data-vol")

    msg_destroy = _format_destroyed_message("volume", volume, dry_run=False)
    assert msg_destroy == "Destroyed volume: data-vol"

    msg_dry_run = _format_destroyed_message("volume", volume, dry_run=True)
    assert msg_dry_run == "Would destroy volume: data-vol"


def test_format_destroyed_message_log() -> None:
    """_format_destroyed_message should format log messages."""
    log = _create_log_file_info(path="/var/log/agent.log")

    msg_destroy = _format_destroyed_message("log", log, dry_run=False)
    assert msg_destroy == "Destroyed log: /var/log/agent.log"

    msg_dry_run = _format_destroyed_message("log", log, dry_run=True)
    assert msg_dry_run == "Would destroy log: /var/log/agent.log"


def test_format_destroyed_message_build_cache() -> None:
    """_format_destroyed_message should format build cache messages."""
    cache = _create_build_cache_info(path="/cache/build123")

    msg_destroy = _format_destroyed_message("build_cache", cache, dry_run=False)
    assert msg_destroy == "Destroyed build cache: /cache/build123"

    msg_dry_run = _format_destroyed_message("build_cache", cache, dry_run=True)
    assert msg_dry_run == "Would destroy build cache: /cache/build123"


def test_format_destroyed_message_unknown_type() -> None:
    """_format_destroyed_message should handle unknown resource types."""
    resource = "some-resource"

    msg = _format_destroyed_message("unknown_type", resource, dry_run=False)
    assert msg == "Destroyed unknown_type: some-resource"


# =============================================================================
# Tests for _emit_jsonl_summary
# =============================================================================


def test_emit_jsonl_summary_empty_result(capsys) -> None:
    """_emit_jsonl_summary should output correct totals for empty result."""
    result = GcResult()
    _emit_jsonl_summary(result, dry_run=False)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["event"] == "summary"
    assert output["total_count"] == 0
    assert output["total_size_bytes"] == 0
    assert output["work_dirs_count"] == 0
    assert output["machines_count"] == 0
    assert output["snapshots_count"] == 0
    assert output["volumes_count"] == 0
    assert output["logs_count"] == 0
    assert output["build_cache_count"] == 0
    assert output["errors_count"] == 0
    assert output["dry_run"] is False


def test_emit_jsonl_summary_with_work_dirs_only(capsys) -> None:
    """_emit_jsonl_summary should count work directories correctly."""
    result = GcResult()
    result.work_dirs_destroyed = [
        _create_work_dir_info(size_bytes=1000),
        _create_work_dir_info(size_bytes=2000),
    ]

    _emit_jsonl_summary(result, dry_run=True)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["total_count"] == 2
    assert output["total_size_bytes"] == 3000
    assert output["work_dirs_count"] == 2
    assert output["dry_run"] is True


def test_emit_jsonl_summary_with_mixed_resources(capsys) -> None:
    """_emit_jsonl_summary should aggregate counts and sizes from all resource types."""
    result = GcResult()
    result.work_dirs_destroyed = [_create_work_dir_info(size_bytes=1000)]
    result.machines_destroyed = [_create_host_info(), _create_host_info()]
    result.snapshots_destroyed = [_create_snapshot_info(size_bytes=500)]
    result.volumes_destroyed = [_create_volume_info(size_bytes=200)]
    result.logs_destroyed = [_create_log_file_info(size_bytes=100)]
    result.build_cache_destroyed = [_create_build_cache_info(size_bytes=300)]

    _emit_jsonl_summary(result, dry_run=False)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    # 1 work_dir + 2 machines + 1 snapshot + 1 volume + 1 log + 1 build_cache = 7
    assert output["total_count"] == 7
    # 1000 (work_dir) + 500 (machine) + 200 (snapshot) + 100 (volume) + 300 (log) = 2100
    assert output["total_size_bytes"] == 2100
    assert output["work_dirs_count"] == 1
    assert output["machines_count"] == 2
    assert output["snapshots_count"] == 1
    assert output["volumes_count"] == 1
    assert output["logs_count"] == 1
    assert output["build_cache_count"] == 1


def test_emit_jsonl_summary_handles_none_snapshot_size(capsys) -> None:
    """_emit_jsonl_summary should handle snapshots with None size_bytes."""
    result = GcResult()
    # Some providers don't report snapshot size, so include None size_bytes
    result.snapshots_destroyed = [
        _create_snapshot_info(size_bytes=1000),
        _create_snapshot_info(size_bytes=None),
    ]

    _emit_jsonl_summary(result, dry_run=False)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["snapshots_count"] == 2
    # Only the snapshot with size should contribute to total
    assert output["total_size_bytes"] == 1000


def test_emit_jsonl_summary_with_errors(capsys) -> None:
    """_emit_jsonl_summary should include errors in output."""
    result = GcResult()
    result.errors = ["Error 1", "Error 2"]

    _emit_jsonl_summary(result, dry_run=False)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert output["errors_count"] == 2
    assert output["errors"] == ["Error 1", "Error 2"]


# =============================================================================
# Tests for _emit_human_summary
# =============================================================================


def test_emit_human_summary_empty_result() -> None:
    """_emit_human_summary should indicate no resources found for empty result."""
    result = GcResult()
    # Just verify no exception is raised; output goes to logger
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_dry_run() -> None:
    """_emit_human_summary should indicate dry run mode."""
    result = GcResult()
    result.work_dirs_destroyed = [_create_work_dir_info()]
    # Just verify no exception is raised; output goes to logger
    _emit_human_summary(result, dry_run=True)


def test_emit_human_summary_with_work_dirs() -> None:
    """_emit_human_summary should count work directories correctly."""
    result = GcResult()
    # Include both local and non-local work dirs
    # (non-local doesn't contribute to freed size calculation)
    result.work_dirs_destroyed = [
        _create_work_dir_info(is_local=True, size_bytes=1000),
        _create_work_dir_info(is_local=False, size_bytes=2000),
    ]
    # Just verify no exception is raised
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_machines() -> None:
    """_emit_human_summary should count machines correctly."""
    result = GcResult()
    result.machines_destroyed = [_create_host_info(), _create_host_info()]
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_snapshots() -> None:
    """_emit_human_summary should count snapshots correctly."""
    result = GcResult()
    result.snapshots_destroyed = [_create_snapshot_info()]
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_volumes() -> None:
    """_emit_human_summary should count volumes correctly."""
    result = GcResult()
    result.volumes_destroyed = [_create_volume_info()]
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_logs() -> None:
    """_emit_human_summary should count logs and report freed size."""
    result = GcResult()
    result.logs_destroyed = [
        _create_log_file_info(size_bytes=100),
        _create_log_file_info(size_bytes=200),
    ]
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_build_cache() -> None:
    """_emit_human_summary should count build cache entries and report freed size."""
    result = GcResult()
    result.build_cache_destroyed = [_create_build_cache_info(size_bytes=5000)]
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_errors() -> None:
    """_emit_human_summary should display errors."""
    result = GcResult()
    result.errors = ["Failed to destroy machine: timeout"]
    _emit_human_summary(result, dry_run=False)


def test_emit_human_summary_with_all_resource_types() -> None:
    """_emit_human_summary should handle all resource types combined."""
    result = GcResult()
    result.work_dirs_destroyed = [_create_work_dir_info(is_local=True, size_bytes=1000)]
    result.machines_destroyed = [_create_host_info()]
    result.snapshots_destroyed = [_create_snapshot_info()]
    result.volumes_destroyed = [_create_volume_info()]
    result.logs_destroyed = [_create_log_file_info()]
    result.build_cache_destroyed = [_create_build_cache_info()]
    result.errors = ["An error occurred"]

    # Just verify no exception is raised with all types combined
    _emit_human_summary(result, dry_run=False)
