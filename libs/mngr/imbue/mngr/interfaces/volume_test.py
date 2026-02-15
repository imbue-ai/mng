from typing import Mapping

import pytest

from imbue.mngr.interfaces.data_types import VolumeFile
from imbue.mngr.interfaces.volume import BaseVolume
from imbue.mngr.interfaces.volume import ScopedVolume
from imbue.mngr.interfaces.volume import _scoped_path


class InMemoryVolume(BaseVolume):
    """In-memory volume implementation for testing."""

    files: dict[str, bytes] = {}

    def listdir(self, path: str) -> list[VolumeFile]:
        path = path.rstrip("/")
        results: list[VolumeFile] = []
        for file_path in sorted(self.files):
            parent = file_path.rsplit("/", 1)[0] if "/" in file_path else ""
            if parent == path or (not path and "/" not in file_path):
                results.append(VolumeFile(path=file_path, mtime=0, size=len(self.files[file_path])))
        return results

    def read_file(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def remove_file(self, path: str) -> None:
        if path not in self.files:
            raise FileNotFoundError(path)
        del self.files[path]

    def write_files(self, file_contents_by_path: Mapping[str, bytes]) -> None:
        self.files.update(file_contents_by_path)


# =============================================================================
# _scoped_path tests
# =============================================================================


def test_scoped_path_prepends_prefix() -> None:
    assert _scoped_path("/data", "file.txt") == "/data/file.txt"


def test_scoped_path_strips_leading_slash_from_path() -> None:
    assert _scoped_path("/data", "/file.txt") == "/data/file.txt"


def test_scoped_path_returns_prefix_for_empty_path() -> None:
    assert _scoped_path("/data", "") == "/data"


def test_scoped_path_returns_prefix_for_slash_only() -> None:
    assert _scoped_path("/data", "/") == "/data"


def test_scoped_path_handles_nested_paths() -> None:
    assert _scoped_path("/data", "sub/dir/file.txt") == "/data/sub/dir/file.txt"


# =============================================================================
# BaseVolume.scoped tests
# =============================================================================


def test_base_volume_scoped_returns_scoped_volume() -> None:
    vol = InMemoryVolume(files={"/host/file.txt": b"hello"})
    scoped = vol.scoped("/host")
    assert isinstance(scoped, ScopedVolume)


# =============================================================================
# ScopedVolume tests
# =============================================================================


@pytest.fixture()
def volume_with_files() -> InMemoryVolume:
    return InMemoryVolume(
        files={
            "/host/data.json": b'{"key": "value"}',
            "/host/agents/a1.json": b'{"id": "a1"}',
            "/host/agents/a2.json": b'{"id": "a2"}',
            "/other/file.txt": b"other",
        }
    )


def test_scoped_volume_read_file(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host")
    assert scoped.read_file("data.json") == b'{"key": "value"}'


def test_scoped_volume_read_file_strips_leading_slash(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host")
    assert scoped.read_file("/data.json") == b'{"key": "value"}'


def test_scoped_volume_write_files(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host")
    scoped.write_files({"new.txt": b"new content"})
    assert volume_with_files.files["/host/new.txt"] == b"new content"


def test_scoped_volume_remove_file(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host")
    scoped.remove_file("data.json")
    assert "/host/data.json" not in volume_with_files.files


def test_scoped_volume_listdir(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host")
    entries = scoped.listdir("agents")
    paths = [e.path for e in entries]
    assert "/host/agents/a1.json" in paths
    assert "/host/agents/a2.json" in paths


def test_scoped_volume_chained_scoping(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host").scoped("agents")
    assert scoped.read_file("a1.json") == b'{"id": "a1"}'


def test_scoped_volume_read_nonexistent_raises(volume_with_files: InMemoryVolume) -> None:
    scoped = volume_with_files.scoped("/host")
    with pytest.raises(FileNotFoundError):
        scoped.read_file("nonexistent.txt")


def test_scoped_volume_prefix_trailing_slash_stripped() -> None:
    vol = InMemoryVolume(files={"/data/file.txt": b"content"})
    scoped = ScopedVolume(delegate=vol, prefix="/data/")
    assert scoped.read_file("file.txt") == b"content"


# =============================================================================
# VolumeFile tests
# =============================================================================


def test_volume_file_fields() -> None:
    vf = VolumeFile(path="/test.txt", mtime=1000, size=42)
    assert vf.path == "/test.txt"
    assert vf.mtime == 1000
    assert vf.size == 42
