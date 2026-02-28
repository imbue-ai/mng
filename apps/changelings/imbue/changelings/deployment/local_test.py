import json
import subprocess
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path

import pytest

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.deployment.local import AgentIdLookupError
from imbue.changelings.deployment.local import MngCreateError
from imbue.changelings.deployment.local import MngNotFoundError
from imbue.changelings.deployment.local import UpdateResult
from imbue.changelings.deployment.local import _generate_auth_code
from imbue.changelings.deployment.local import _raise_if_agent_exists
from imbue.changelings.deployment.local import _run_mng_command
from imbue.changelings.deployment.local import _verify_mng_available
from imbue.changelings.deployment.local import clone_git_repo
from imbue.changelings.deployment.local import commit_files_in_repo
from imbue.changelings.deployment.local import init_empty_git_repo
from imbue.changelings.deployment.local import update_local
from imbue.changelings.errors import AgentAlreadyExistsError
from imbue.changelings.errors import ChangelingError
from imbue.changelings.errors import GitCloneError
from imbue.changelings.errors import GitCommitError
from imbue.changelings.errors import GitInitError
from imbue.changelings.errors import MngCommandError
from imbue.changelings.primitives import GitUrl
from imbue.changelings.testing import init_and_commit_git_repo
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.event_utils import ReadOnlyEvent
from imbue.concurrency_group.subprocess_utils import FinishedProcess
from imbue.mng.primitives import AgentId


def _make_finished_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    command: tuple[str, ...] = ("mng",),
) -> FinishedProcess:
    return FinishedProcess(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=command,
        is_output_already_logged=False,
    )


class _FakeConcurrencyGroup(ConcurrencyGroup):
    """ConcurrencyGroup subclass that returns pre-configured results instead of running processes.

    Accepts a mapping of command-name -> FinishedProcess so tests can control
    what each mng subcommand returns. Also records the commands that were run
    in order.
    """

    _fake_results: dict[str, FinishedProcess]
    _commands_run: list[list[str]]

    def __init__(self, results: dict[str, FinishedProcess] | None = None) -> None:
        super().__init__(name="fake-cg")
        self._fake_results = results or {}
        self._commands_run = []

    @property
    def commands_run(self) -> list[list[str]]:
        return self._commands_run

    def run_process_to_completion(
        self,
        command: Sequence[str],
        timeout: float | None = None,
        is_checked_after: bool = True,
        on_output: Callable[[str, bool], None] | None = None,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        shutdown_event: ReadOnlyEvent | None = None,
    ) -> FinishedProcess:
        cmd_list = list(command)
        self._commands_run.append(cmd_list)

        # Try to match by the mng subcommand (second element, e.g. "snapshot", "stop")
        if len(cmd_list) > 1 and cmd_list[1] in self._fake_results:
            return self._fake_results[cmd_list[1]]

        # Default: success
        return _make_finished_process(command=tuple(cmd_list))


def _make_fake_cg(
    agent_id: str | None = None,
    failing_command: str | None = None,
    fail_stderr: str = "command failed",
) -> _FakeConcurrencyGroup:
    """Create a _FakeConcurrencyGroup configured for testing.

    By default, all commands succeed. The `list` command returns a JSON response
    with the given agent_id (or a generated one). If failing_command is provided,
    that specific mng subcommand will return exit code 1.
    """
    resolved_agent_id = agent_id or str(AgentId())

    results: dict[str, FinishedProcess] = {
        "list": _make_finished_process(
            stdout=json.dumps({"agents": [{"id": resolved_agent_id, "name": "my-agent"}]}),
            command=("mng", "list"),
        ),
    }

    if failing_command is not None:
        results[failing_command] = _make_finished_process(
            returncode=1,
            stderr=fail_stderr,
            command=("mng", failing_command, "my-agent"),
        )

    return _FakeConcurrencyGroup(results=results)


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


def test_clone_git_repo_clones_local_repo(tmp_path: Path) -> None:
    """Verify that clone_git_repo clones a local git repo into the given directory."""
    repo_dir = tmp_path / "source-repo"
    repo_dir.mkdir()
    (repo_dir / "hello.txt").write_text("hello")
    init_and_commit_git_repo(repo_dir, tmp_path)

    clone_dir = tmp_path / "my-clone"
    clone_git_repo(GitUrl(str(repo_dir)), clone_dir)

    assert clone_dir.is_dir()
    assert (clone_dir / "hello.txt").read_text() == "hello"
    assert (clone_dir / ".git").is_dir()


def test_clone_git_repo_raises_for_invalid_url(tmp_path: Path) -> None:
    """Verify that clone_git_repo raises GitCloneError for an invalid URL."""
    clone_dir = tmp_path / "bad-clone"
    with pytest.raises(GitCloneError, match="git clone failed"):
        clone_git_repo(GitUrl("/nonexistent/repo/path"), clone_dir)


# --- init_empty_git_repo tests ---


def test_init_empty_git_repo_creates_git_directory(tmp_path: Path) -> None:
    """Verify that init_empty_git_repo creates a .git directory."""
    repo_dir = tmp_path / "new-repo"
    init_empty_git_repo(repo_dir)

    assert repo_dir.is_dir()
    assert (repo_dir / ".git").is_dir()


def test_init_empty_git_repo_creates_parent_dirs(tmp_path: Path) -> None:
    """Verify that init_empty_git_repo creates parent directories if needed."""
    repo_dir = tmp_path / "nested" / "dir" / "repo"
    init_empty_git_repo(repo_dir)

    assert repo_dir.is_dir()
    assert (repo_dir / ".git").is_dir()


def test_git_init_error_is_changeling_error() -> None:
    err = GitInitError("test")
    assert isinstance(err, ChangelingError)


# --- commit_files_in_repo tests ---


def test_commit_files_in_repo_commits_new_files(tmp_path: Path) -> None:
    """Verify that commit_files_in_repo stages and commits files."""
    repo_dir = tmp_path / "repo"
    init_empty_git_repo(repo_dir)

    (repo_dir / "hello.txt").write_text("hello")

    committed = commit_files_in_repo(repo_dir, "test commit")

    assert committed is True

    # Verify the file is tracked
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    assert "test commit" in result.stdout


def test_commit_files_in_repo_returns_false_when_nothing_to_commit(tmp_path: Path) -> None:
    """Verify that commit_files_in_repo returns False when there are no changes."""
    repo_dir = tmp_path / "repo"
    init_empty_git_repo(repo_dir)

    # Create a file and commit it first
    (repo_dir / "hello.txt").write_text("hello")
    commit_files_in_repo(repo_dir, "first commit")

    # Now try to commit again with no changes
    committed = commit_files_in_repo(repo_dir, "empty commit")
    assert committed is False


def test_git_commit_error_is_changeling_error() -> None:
    err = GitCommitError("test")
    assert isinstance(err, ChangelingError)


# --- UpdateResult tests ---


def test_update_result_fields() -> None:
    result = UpdateResult(
        agent_name="my-agent",
        did_snapshot=True,
        did_push=False,
        did_provision=True,
    )
    assert result.agent_name == "my-agent"
    assert result.did_snapshot is True
    assert result.did_push is False
    assert result.did_provision is True


# --- MngCommandError tests ---


def test_mng_command_error_is_changeling_error() -> None:
    err = MngCommandError("test")
    assert isinstance(err, ChangelingError)


# --- _run_mng_command tests ---


def test_run_mng_command_raises_on_failure() -> None:
    """Verify that _run_mng_command raises MngCommandError when the command fails."""
    cg = _FakeConcurrencyGroup(
        results={
            "stop": _make_finished_process(
                returncode=1,
                stderr="something went wrong",
                command=("mng", "stop", "my-agent"),
            ),
        }
    )

    with pytest.raises(MngCommandError, match="mng stop failed"):
        _run_mng_command(
            command_name="stop",
            args=["stop", "my-agent"],
            concurrency_group=cg,
        )


def test_run_mng_command_succeeds_on_zero_exit() -> None:
    """Verify that _run_mng_command does not raise when the command succeeds."""
    cg = _FakeConcurrencyGroup()

    _run_mng_command(
        command_name="stop",
        args=["stop", "my-agent"],
        concurrency_group=cg,
    )


def test_run_mng_command_includes_stderr_in_error() -> None:
    """Verify that the error message includes stderr output."""
    cg = _FakeConcurrencyGroup(
        results={
            "snapshot": _make_finished_process(
                returncode=1,
                stderr="detailed error info",
                command=("mng", "snapshot", "my-agent"),
            ),
        }
    )

    with pytest.raises(MngCommandError, match="detailed error info"):
        _run_mng_command(
            command_name="snapshot",
            args=["snapshot", "my-agent"],
            concurrency_group=cg,
        )


def test_run_mng_command_falls_back_to_stdout_in_error() -> None:
    """Verify that when stderr is empty, stdout is used in the error message."""
    cg = _FakeConcurrencyGroup(
        results={
            "push": _make_finished_process(
                returncode=1,
                stdout="stdout error info",
                stderr="",
                command=("mng", "push", "my-agent"),
            ),
        }
    )

    with pytest.raises(MngCommandError, match="stdout error info"):
        _run_mng_command(
            command_name="push",
            args=["push", "my-agent"],
            concurrency_group=cg,
        )


def test_run_mng_command_records_command() -> None:
    """Verify that _run_mng_command passes the correct command to the concurrency group."""
    cg = _FakeConcurrencyGroup()

    _run_mng_command(
        command_name="stop",
        args=["stop", "my-agent"],
        concurrency_group=cg,
    )

    assert len(cg.commands_run) == 1
    assert cg.commands_run[0] == ["mng", "stop", "my-agent"]


# --- update_local tests ---


def test_update_local_all_steps_enabled() -> None:
    """Verify that all mng commands are called when all flags are True."""
    cg = _make_fake_cg()

    result = update_local(
        agent_name="my-agent",
        do_snapshot=True,
        do_push=True,
        do_provision=True,
        concurrency_group=cg,
    )

    assert result.agent_name == "my-agent"
    assert result.did_snapshot is True
    assert result.did_push is True
    assert result.did_provision is True

    # Verify all expected commands were called
    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert "list" in subcommands
    assert "snapshot" in subcommands
    assert "stop" in subcommands
    assert "push" in subcommands
    assert "provision" in subcommands
    assert "start" in subcommands


def test_update_local_skips_snapshot_when_disabled() -> None:
    """Verify that snapshot is skipped when do_snapshot is False."""
    cg = _make_fake_cg()

    result = update_local(
        agent_name="my-agent",
        do_snapshot=False,
        do_push=True,
        do_provision=True,
        concurrency_group=cg,
    )

    assert result.did_snapshot is False
    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert "snapshot" not in subcommands


def test_update_local_skips_push_when_disabled() -> None:
    """Verify that push is skipped when do_push is False."""
    cg = _make_fake_cg()

    result = update_local(
        agent_name="my-agent",
        do_snapshot=True,
        do_push=False,
        do_provision=True,
        concurrency_group=cg,
    )

    assert result.did_push is False
    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert "push" not in subcommands


def test_update_local_skips_provision_when_disabled() -> None:
    """Verify that provision is skipped when do_provision is False."""
    cg = _make_fake_cg()

    result = update_local(
        agent_name="my-agent",
        do_snapshot=True,
        do_push=True,
        do_provision=False,
        concurrency_group=cg,
    )

    assert result.did_provision is False
    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert "provision" not in subcommands


def test_update_local_all_optional_steps_disabled() -> None:
    """Verify that only stop and start are called when all optional flags are False."""
    cg = _make_fake_cg()

    result = update_local(
        agent_name="my-agent",
        do_snapshot=False,
        do_push=False,
        do_provision=False,
        concurrency_group=cg,
    )

    assert result.did_snapshot is False
    assert result.did_push is False
    assert result.did_provision is False

    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert "snapshot" not in subcommands
    assert "push" not in subcommands
    assert "provision" not in subcommands
    assert "stop" in subcommands
    assert "start" in subcommands


def test_update_local_stop_and_start_always_run() -> None:
    """Verify that stop and start always execute regardless of flags."""
    cg = _make_fake_cg()

    update_local(
        agent_name="my-agent",
        do_snapshot=False,
        do_push=False,
        do_provision=False,
        concurrency_group=cg,
    )

    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert "stop" in subcommands
    assert "start" in subcommands


def test_update_local_raises_when_agent_not_found() -> None:
    """Verify that update_local raises AgentIdLookupError when agent is not found."""
    cg = _FakeConcurrencyGroup(
        results={
            "list": _make_finished_process(
                stdout=json.dumps({"agents": []}),
                command=("mng", "list"),
            ),
        }
    )

    with pytest.raises(AgentIdLookupError, match="No agent found"):
        update_local(
            agent_name="ghost",
            do_snapshot=True,
            do_push=True,
            do_provision=True,
            concurrency_group=cg,
        )


def test_update_local_raises_when_stop_fails() -> None:
    """Verify that update_local raises when mng stop fails."""
    cg = _make_fake_cg(failing_command="stop", fail_stderr="agent not responding")

    with pytest.raises(MngCommandError, match="mng stop failed"):
        update_local(
            agent_name="my-agent",
            do_snapshot=True,
            do_push=True,
            do_provision=True,
            concurrency_group=cg,
        )


def test_update_local_raises_when_snapshot_fails() -> None:
    """Verify that update_local raises when mng snapshot fails."""
    cg = _make_fake_cg(failing_command="snapshot", fail_stderr="snapshots not supported")

    with pytest.raises(MngCommandError, match="mng snapshot failed"):
        update_local(
            agent_name="my-agent",
            do_snapshot=True,
            do_push=True,
            do_provision=True,
            concurrency_group=cg,
        )


def test_update_local_raises_when_push_fails() -> None:
    """Verify that update_local raises when mng push fails."""
    cg = _make_fake_cg(failing_command="push", fail_stderr="push error")

    with pytest.raises(MngCommandError, match="mng push failed"):
        update_local(
            agent_name="my-agent",
            do_snapshot=True,
            do_push=True,
            do_provision=True,
            concurrency_group=cg,
        )


def test_update_local_raises_when_start_fails() -> None:
    """Verify that update_local raises when mng start fails."""
    cg = _make_fake_cg(failing_command="start", fail_stderr="start error")

    with pytest.raises(MngCommandError, match="mng start failed"):
        update_local(
            agent_name="my-agent",
            do_snapshot=True,
            do_push=True,
            do_provision=True,
            concurrency_group=cg,
        )


def test_update_local_executes_steps_in_correct_order() -> None:
    """Verify that update steps execute in the correct order."""
    cg = _make_fake_cg()

    update_local(
        agent_name="my-agent",
        do_snapshot=True,
        do_push=True,
        do_provision=True,
        concurrency_group=cg,
    )

    # Extract the mng subcommands in order
    subcommands = [cmd[1] for cmd in cg.commands_run if len(cmd) > 1]
    assert subcommands == ["list", "snapshot", "stop", "push", "provision", "start"]


def test_update_local_provision_uses_no_restart_flag() -> None:
    """Verify that provision is called with --no-restart since we start separately."""
    cg = _make_fake_cg()

    update_local(
        agent_name="my-agent",
        do_snapshot=False,
        do_push=False,
        do_provision=True,
        concurrency_group=cg,
    )

    provision_commands = [cmd for cmd in cg.commands_run if len(cmd) > 1 and cmd[1] == "provision"]
    assert len(provision_commands) == 1
    assert "--no-restart" in provision_commands[0]
