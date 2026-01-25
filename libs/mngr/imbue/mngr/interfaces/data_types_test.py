from pathlib import Path
from pathlib import PurePosixPath

import pytest

from imbue.mngr.errors import InvalidRelativePathError
from imbue.mngr.interfaces.data_types import RelativePath


def test_relative_path_accepts_relative_string() -> None:
    """RelativePath should accept a relative path string."""
    path = RelativePath("some/relative/path.txt")
    assert str(path) == "some/relative/path.txt"


def test_relative_path_accepts_relative_path_object() -> None:
    """RelativePath should accept a relative Path object."""
    path = RelativePath(Path("some/relative/path.txt"))
    assert str(path) == "some/relative/path.txt"


def test_relative_path_rejects_absolute_path_string() -> None:
    """RelativePath should reject an absolute path string."""
    with pytest.raises(InvalidRelativePathError, match="Path must be relative"):
        RelativePath("/absolute/path.txt")


def test_relative_path_rejects_absolute_path_object() -> None:
    """RelativePath should reject an absolute Path object."""
    with pytest.raises(InvalidRelativePathError, match="Path must be relative"):
        RelativePath(Path("/absolute/path.txt"))


def test_relative_path_is_pure_posix_path() -> None:
    """RelativePath should be a PurePosixPath subclass for path manipulation."""
    relative_path = RelativePath("some/path.txt")
    assert isinstance(relative_path, PurePosixPath)
    assert relative_path.parent == PurePosixPath("some")
    assert relative_path.name == "path.txt"
    assert relative_path.suffix == ".txt"


def test_relative_path_works_with_path_division() -> None:
    """RelativePath should work with Path / operator for joining."""
    work_dir = Path("/home/user/work")
    relative_path = RelativePath(".claude/config.json")
    result = work_dir / relative_path
    assert result == Path("/home/user/work/.claude/config.json")
