from enum import auto

from pydantic import Field

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel


class PathRelativeTo(UpperCaseStrEnum):
    """Base directory for resolving relative paths on agent targets."""

    WORK = auto()
    STATE = auto()
    HOST = auto()


class FileEntry(FrozenModel):
    """A single file or directory entry from a remote listing."""

    name: str = Field(description="File or directory name")
    path: str = Field(description="Full path on the remote host")
    file_type: str = Field(description="Type: file, directory, symlink, or other")
    size: int | None = Field(default=None, description="Size in bytes (None for directories)")
    modified: str | None = Field(default=None, description="Last modification time as ISO 8601 string")
    permissions: str | None = Field(default=None, description="File permissions string (e.g. -rw-r--r--)")
