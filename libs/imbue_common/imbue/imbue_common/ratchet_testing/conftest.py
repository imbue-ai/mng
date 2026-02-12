from collections.abc import Iterator
from pathlib import Path

import pytest

from imbue.imbue_common.pytest_utils import create_isolated_git_repo


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Create a temporary git repository isolated from host git config.

    Returns the repo directory path. The repo has git init and local
    user.email/user.name configured, but no initial commit -- tests
    create their own files and commits.

    HOME is redirected to a temp directory so that the host's global
    gitconfig (e.g. commit.gpgsign) does not leak into tests.
    """
    yield create_isolated_git_repo(tmp_path, monkeypatch)
