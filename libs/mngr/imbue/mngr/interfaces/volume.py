from abc import ABC
from abc import abstractmethod
from typing import Mapping

from imbue.mngr.interfaces.data_types import VolumeFile


class Volume(ABC):
    """Interface for accessing a volume's files.

    A volume is a persistent, file-system-like store that can be read from
    and written to. Implementations may scope operations to a path prefix
    within a backing store.

    This is the mngr-level volume abstraction. Multiple logical mngr Volumes
    may map to a single provider-level volume (e.g., a root host volume can
    provide scoped-down volumes for individual agents or subfolders).
    """

    @abstractmethod
    def listdir(self, path: str) -> list[VolumeFile]:
        """List file entries in the given directory path on the volume."""
        ...

    @abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read a file from the volume and return its contents as bytes."""
        ...

    @abstractmethod
    def remove_file(self, path: str) -> None:
        """Remove a file from the volume."""
        ...

    @abstractmethod
    def write_files(self, file_contents_by_path: Mapping[str, bytes]) -> None:
        """Write one or more files to the volume."""
        ...

    @abstractmethod
    def scoped(self, prefix: str) -> "Volume":
        """Return a new Volume scoped to the given path prefix.

        All operations on the returned volume will be relative to the prefix.
        """
        ...


class BaseVolume(Volume):
    """Base implementation of Volume that provides scoping via ScopedVolume.

    Concrete volume implementations (ModalVolume, LocalVolume, etc.) should
    inherit from this class rather than from Volume directly.
    """

    def scoped(self, prefix: str) -> "Volume":
        """Return a ScopedVolume that prepends the given prefix to all operations."""
        return ScopedVolume(delegate=self, prefix=prefix)


class ScopedVolume(BaseVolume):
    """A volume that prepends a path prefix to all operations.

    Useful for giving an agent or subsystem a restricted view of a
    larger volume (e.g., a per-host volume scoped to a specific agent's
    subdirectory).
    """

    def __init__(self, delegate: Volume, prefix: str) -> None:
        self._delegate = delegate
        self._prefix = prefix.rstrip("/")

    def _scoped_path(self, path: str) -> str:
        """Prepend the prefix to the given path."""
        path = path.lstrip("/")
        return f"{self._prefix}/{path}" if path else self._prefix

    def listdir(self, path: str) -> list[VolumeFile]:
        return self._delegate.listdir(self._scoped_path(path))

    def read_file(self, path: str) -> bytes:
        return self._delegate.read_file(self._scoped_path(path))

    def remove_file(self, path: str) -> None:
        self._delegate.remove_file(self._scoped_path(path))

    def write_files(self, file_contents_by_path: Mapping[str, bytes]) -> None:
        scoped = {self._scoped_path(p): data for p, data in file_contents_by_path.items()}
        self._delegate.write_files(scoped)

    def scoped(self, prefix: str) -> "Volume":
        combined = f"{self._prefix}/{prefix.lstrip('/')}"
        return ScopedVolume(delegate=self._delegate, prefix=combined)
