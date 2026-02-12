import subprocess
from pathlib import Path

import pytest

from imbue.imbue_common.pure import pure


def create_isolated_git_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Create a temporary git repository isolated from host git config.

    Redirects HOME to a fake directory so that the host's global gitconfig
    (e.g. commit.gpgsign) does not leak into tests, then creates a git repo
    with local user.email and user.name configured.

    Returns the repo directory path. The repo has no initial commit -- callers
    create their own files and commits.
    """
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    return repo_dir


@pure
def inline_snapshot_is_updating(config: pytest.Config) -> bool:
    """Check if inline-snapshot is running with create or fix flags.

    This is useful for tests that need to behave differently when snapshots
    are being created or fixed vs when they are being validated.
    """
    inline_snapshot_flags = config.option.inline_snapshot
    if inline_snapshot_flags is None:
        return False

    flags = inline_snapshot_flags.split(",")
    return "create" in flags or "fix" in flags
