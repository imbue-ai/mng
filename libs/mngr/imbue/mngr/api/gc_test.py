"""Unit tests for gc API functions."""

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

from imbue.mngr.api.gc import _apply_cel_filters
from imbue.mngr.api.gc import _resource_to_cel_context
from imbue.mngr.interfaces.data_types import LogFileInfo
from imbue.mngr.interfaces.data_types import SizeBytes
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
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
