from pathlib import Path

import pytest

from imbue.mngr.interfaces.data_types import VolumeFileType
from imbue.mngr.providers.local.volume import LocalVolume


@pytest.fixture()
def volume(tmp_path: Path) -> LocalVolume:
    root = tmp_path / "vol"
    root.mkdir()
    return LocalVolume(root_path=root)


def test_write_and_read_file(volume: LocalVolume) -> None:
    volume.write_files({"hello.txt": b"world"})
    assert volume.read_file("hello.txt") == b"world"


def test_write_creates_parent_directories(volume: LocalVolume) -> None:
    volume.write_files({"sub/dir/file.txt": b"nested"})
    assert volume.read_file("sub/dir/file.txt") == b"nested"


def test_read_nonexistent_raises(volume: LocalVolume) -> None:
    with pytest.raises(FileNotFoundError):
        volume.read_file("nonexistent.txt")


def test_listdir_returns_files_and_directories(volume: LocalVolume) -> None:
    volume.write_files({"a.txt": b"aaa", "sub/b.txt": b"bb"})
    entries = volume.listdir("")
    paths = [e.path for e in entries]
    assert "a.txt" in paths
    file_types = {e.path: e.file_type for e in entries}
    assert file_types["a.txt"] == VolumeFileType.FILE
    assert file_types["sub"] == VolumeFileType.DIRECTORY


def test_listdir_empty_dir(volume: LocalVolume) -> None:
    entries = volume.listdir("")
    assert entries == []


def test_listdir_nonexistent_dir(volume: LocalVolume) -> None:
    entries = volume.listdir("does_not_exist")
    assert entries == []


def test_remove_file(volume: LocalVolume) -> None:
    volume.write_files({"remove_me.txt": b"bye"})
    assert volume.read_file("remove_me.txt") == b"bye"
    volume.remove_file("remove_me.txt")
    with pytest.raises(FileNotFoundError):
        volume.read_file("remove_me.txt")


def test_remove_nonexistent_raises(volume: LocalVolume) -> None:
    with pytest.raises(FileNotFoundError):
        volume.remove_file("no_such_file.txt")


def test_scoped_volume(volume: LocalVolume) -> None:
    volume.write_files({"agents/a1/data.json": b'{"id":"a1"}'})
    scoped = volume.scoped("agents/a1")
    assert scoped.read_file("data.json") == b'{"id":"a1"}'


def test_write_multiple_files(volume: LocalVolume) -> None:
    volume.write_files(
        {
            "one.txt": b"1",
            "two.txt": b"2",
            "three.txt": b"3",
        }
    )
    assert volume.read_file("one.txt") == b"1"
    assert volume.read_file("two.txt") == b"2"
    assert volume.read_file("three.txt") == b"3"


def test_listdir_includes_size(volume: LocalVolume) -> None:
    volume.write_files({"sized.txt": b"hello"})
    entries = [e for e in volume.listdir("") if e.file_type == VolumeFileType.FILE]
    assert len(entries) == 1
    assert entries[0].size == 5
