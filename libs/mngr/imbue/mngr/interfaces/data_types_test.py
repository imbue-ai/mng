from pathlib import Path

import pytest

from imbue.mngr.errors import InvalidRelativePathError
from imbue.mngr.interfaces.data_types import RelativePath


def test_relative_path_accepts_relative_string() -> None:
    """RelativePath should accept a relative path string."""
    path = RelativePath("some/relative/path.txt")
    assert path == "some/relative/path.txt"


def test_relative_path_accepts_relative_path_object() -> None:
    """RelativePath should accept a relative Path object."""
    path = RelativePath(Path("some/relative/path.txt"))
    assert path == "some/relative/path.txt"


def test_relative_path_rejects_absolute_path_string() -> None:
    """RelativePath should reject an absolute path string."""
    with pytest.raises(InvalidRelativePathError, match="Path must be relative"):
        RelativePath("/absolute/path.txt")


def test_relative_path_rejects_absolute_path_object() -> None:
    """RelativePath should reject an absolute Path object."""
    with pytest.raises(InvalidRelativePathError, match="Path must be relative"):
        RelativePath(Path("/absolute/path.txt"))


def test_relative_path_to_path_returns_path_object() -> None:
    """RelativePath.to_path() should return a Path object."""
    relative_path = RelativePath("some/path.txt")
    path_obj = relative_path.to_path()
    assert isinstance(path_obj, Path)
    assert path_obj == Path("some/path.txt")
