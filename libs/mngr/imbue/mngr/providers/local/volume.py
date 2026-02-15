from pathlib import Path
from typing import Mapping

from pydantic import Field

from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.data_types import VolumeFile
from imbue.mngr.interfaces.data_types import VolumeFileType
from imbue.mngr.interfaces.volume import BaseVolume


class LocalVolume(BaseVolume):
    """Volume implementation backed by a local filesystem directory.

    All paths are resolved relative to root_path.
    """

    root_path: Path = Field(frozen=True, description="Root directory on the local filesystem")

    def _resolve(self, path: str) -> Path:
        """Resolve a volume path to a local filesystem path.

        Raises ValueError if the resolved path escapes the root directory
        (e.g., via '..' components).
        """
        resolved = (self.root_path / path.lstrip("/")).resolve()
        root_resolved = self.root_path.resolve()
        if not resolved.is_relative_to(root_resolved):
            raise MngrError(f"Path '{path}' escapes volume root")
        return resolved

    def listdir(self, path: str) -> list[VolumeFile]:
        resolved = self._resolve(path)
        if not resolved.is_dir():
            return []
        entries: list[VolumeFile] = []
        for child in sorted(resolved.iterdir()):
            stat = child.stat()
            file_type = VolumeFileType.DIRECTORY if child.is_dir() else VolumeFileType.FILE
            entries.append(
                VolumeFile(
                    path=str(child.relative_to(self.root_path)),
                    file_type=file_type,
                    mtime=int(stat.st_mtime),
                    size=stat.st_size,
                )
            )
        return entries

    def read_file(self, path: str) -> bytes:
        resolved = self._resolve(path)
        return resolved.read_bytes()

    def remove_file(self, path: str) -> None:
        resolved = self._resolve(path)
        resolved.unlink()

    def write_files(self, file_contents_by_path: Mapping[str, bytes]) -> None:
        for file_path, data in file_contents_by_path.items():
            resolved = self._resolve(file_path)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(data)
