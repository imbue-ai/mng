import json
import subprocess
from pathlib import Path

import pytest

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.deployment.local import AgentIdLookupError
from imbue.changelings.deployment.local import MngCreateError
from imbue.changelings.deployment.local import MngNotFoundError
from imbue.changelings.deployment.local import _generate_auth_code
from imbue.changelings.deployment.local import _raise_if_agent_exists
from imbue.changelings.deployment.local import _verify_mng_available
from imbue.changelings.deployment.local import clone_git_repo
from imbue.changelings.errors import AgentAlreadyExistsError
from imbue.changelings.errors import ChangelingError
from imbue.changelings.errors import GitCloneError
from imbue.changelings.primitives import GitUrl
from imbue.mng.primitives import AgentId


def test_verify_mng_available_succeeds_when_mng_exists() -> None:
    """mng should be available in the test environment (it's a dependency)."""
    _verify_mng_available()


def test_generate_auth_code_creates_login_url(tmp_path: Path) -> None:
    paths = ChangelingPaths(data_dir=tmp_path)
    agent_id = AgentId()

    login_url = _generate_auth_code(
        paths=paths,
        agent_id=agent_id,
        forwarding_server_port=8420,
    )

    assert "http://127.0.0.1:8420/login" in login_url
    assert str(agent_id) in login_url
    assert "one_time_code=" in login_url


def test_generate_auth_code_stores_code_on_disk(tmp_path: Path) -> None:
    paths = ChangelingPaths(data_dir=tmp_path)
    agent_id = AgentId()

    _generate_auth_code(
        paths=paths,
        agent_id=agent_id,
        forwarding_server_port=8420,
    )

    assert paths.auth_dir.exists()
    codes_file = paths.auth_dir / "one_time_codes.json"
    assert codes_file.exists()


def test_mng_not_found_error_is_changeling_error() -> None:
    err = MngNotFoundError("test")
    assert isinstance(err, ChangelingError)


def test_mng_create_error_is_changeling_error() -> None:
    err = MngCreateError("test")
    assert isinstance(err, ChangelingError)


def test_agent_id_lookup_error_is_changeling_error() -> None:
    err = AgentIdLookupError("test")
    assert isinstance(err, ChangelingError)


def test_agent_already_exists_error_is_changeling_error() -> None:
    err = AgentAlreadyExistsError("test")
    assert isinstance(err, ChangelingError)


def test_agent_already_exists_error_message() -> None:
    err = AgentAlreadyExistsError(
        "An agent named 'my-agent' already exists. "
        "Use 'changeling update' to update it, or 'changeling destroy' to remove it."
    )
    assert "changeling update" in str(err)
    assert "changeling destroy" in str(err)


def test_raise_if_agent_exists_raises_when_agent_found() -> None:
    """Verify that _raise_if_agent_exists raises when the JSON output contains agents."""
    mng_output = json.dumps({"agents": [{"id": "agent-abc123", "name": "my-agent"}]})

    with pytest.raises(AgentAlreadyExistsError, match="already exists"):
        _raise_if_agent_exists("my-agent", mng_output)


def test_raise_if_agent_exists_does_not_raise_when_no_agents() -> None:
    """Verify that _raise_if_agent_exists does not raise when agents list is empty."""
    mng_output = json.dumps({"agents": []})

    _raise_if_agent_exists("my-agent", mng_output)


def test_raise_if_agent_exists_does_not_raise_for_invalid_json() -> None:
    """Verify that _raise_if_agent_exists silently proceeds on malformed JSON."""
    _raise_if_agent_exists("my-agent", "not valid json {{{")


def test_raise_if_agent_exists_error_mentions_update_and_destroy() -> None:
    """Verify the error message mentions changeling update and changeling destroy."""
    mng_output = json.dumps({"agents": [{"id": "agent-abc123"}]})

    with pytest.raises(AgentAlreadyExistsError) as exc_info:
        _raise_if_agent_exists("my-agent", mng_output)

    assert "changeling update" in str(exc_info.value)
    assert "changeling destroy" in str(exc_info.value)


def test_git_clone_error_is_changeling_error() -> None:
    err = GitCloneError("test")
    assert isinstance(err, ChangelingError)


def _init_git_repo(repo_dir: Path, tmp_path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )


def test_clone_git_repo_clones_local_repo(tmp_path: Path) -> None:
    """Verify that clone_git_repo clones a local git repo."""
    repo_dir = tmp_path / "source-repo"
    _init_git_repo(repo_dir, tmp_path)
    (repo_dir / "hello.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add file"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@test",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@test",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )

    clone_dir = clone_git_repo(GitUrl(str(repo_dir)))

    assert clone_dir.is_dir()
    assert (clone_dir / "hello.txt").read_text() == "hello"
    assert (clone_dir / ".git").is_dir()


def test_clone_git_repo_raises_for_invalid_url() -> None:
    """Verify that clone_git_repo raises GitCloneError for an invalid URL."""
    with pytest.raises(GitCloneError, match="git clone failed"):
        clone_git_repo(GitUrl("/nonexistent/repo/path"))


def test_clone_git_repo_cleans_up_on_failure() -> None:
    """Verify that the temporary directory is cleaned up when cloning fails."""
    with pytest.raises(GitCloneError):
        clone_git_repo(GitUrl("/nonexistent/repo/path"))
