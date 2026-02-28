import os
import stat
from pathlib import Path

import pytest

from imbue.mng.utils.file_utils import atomic_write


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "output.txt"

    atomic_write(target, "hello")

    assert target.read_text() == "hello"


def test_atomic_write_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "output.txt"
    target.write_text("old content")

    atomic_write(target, "new content")

    assert target.read_text() == "new content"


def test_atomic_write_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c" / "output.txt"

    atomic_write(target, "nested")

    assert target.read_text() == "nested"


def test_atomic_write_preserves_existing_permissions(tmp_path: Path) -> None:
    target = tmp_path / "output.txt"
    target.write_text("original")
    os.chmod(target, 0o644)

    atomic_write(target, "updated")

    actual_mode = stat.S_IMODE(target.stat().st_mode)
    assert actual_mode == 0o644


def test_atomic_write_preserves_readonly_permissions(tmp_path: Path) -> None:
    target = tmp_path / "output.txt"
    target.write_text("original")
    os.chmod(target, 0o444)

    atomic_write(target, "updated")

    actual_mode = stat.S_IMODE(target.stat().st_mode)
    assert actual_mode == 0o444


def test_atomic_write_new_file_gets_default_permissions(tmp_path: Path) -> None:
    target = tmp_path / "new_file.txt"

    atomic_write(target, "content")

    actual_mode = stat.S_IMODE(target.stat().st_mode)
    assert actual_mode == 0o600


@pytest.mark.skipif(os.geteuid() == 0, reason="Root bypasses permission checks")
def test_atomic_write_raises_on_unwritable_directory(tmp_path: Path) -> None:
    locked_dir = tmp_path / "locked"
    locked_dir.mkdir()
    os.chmod(locked_dir, 0o555)

    target = locked_dir / "subdir" / "output.txt"
    try:
        with pytest.raises(OSError):
            atomic_write(target, "content")
    finally:
        os.chmod(locked_dir, 0o755)
