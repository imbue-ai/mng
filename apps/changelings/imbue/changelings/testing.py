from pathlib import Path
from typing import Final

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup

_GIT_TEST_ENV_KEYS: Final[dict[str, str]] = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@test",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@test",
}


def _git_test_env(tmp_path: Path) -> dict[str, str]:
    """Build an environment dict for git commands in tests.

    Uses deterministic author/committer info and a minimal PATH so that
    git operations are reproducible and don't depend on the user's config.
    """
    return {
        **_GIT_TEST_ENV_KEYS,
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }


def init_and_commit_git_repo(repo_dir: Path, tmp_path: Path, allow_empty: bool = False) -> None:
    """Initialize a git repo and commit all files in repo_dir.

    If allow_empty is True, creates an empty commit even when there are no
    staged files. Otherwise, all files in the directory are staged and committed.
    """
    cg = ConcurrencyGroup(name="test-git-init")
    with cg:
        cg.run_process_to_completion(command=["git", "init"], cwd=repo_dir)
        cg.run_process_to_completion(command=["git", "add", "."], cwd=repo_dir)

        commit_cmd = ["git", "commit", "-m", "init"]
        if allow_empty:
            commit_cmd.append("--allow-empty")

        cg.run_process_to_completion(
            command=commit_cmd,
            cwd=repo_dir,
            env=_git_test_env(tmp_path),
        )
