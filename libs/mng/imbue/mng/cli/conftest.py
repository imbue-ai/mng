from collections.abc import Callable
from pathlib import Path
from typing import Generator

import pluggy
import pytest
from click.testing import CliRunner

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.cli.connect import ConnectCliOptions
from imbue.mng.cli.create import CreateCliOptions
from imbue.mng.testing import cleanup_tmux_session
from imbue.mng.testing import create_test_agent_via_cli


@pytest.fixture
def default_create_cli_opts() -> CreateCliOptions:
    """Baseline CreateCliOptions with sensible defaults for all fields.

    Tests use .model_copy_update() with to_update_dict() to override only the fields
    relevant to each test case.
    """
    return CreateCliOptions(
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
        positional_name=None,
        positional_agent_type=None,
        agent_args=(),
        template=(),
        agent_type=None,
        reuse=False,
        connect=True,
        await_ready=None,
        await_agent_stopped=None,
        copy_work_dir=None,
        ensure_clean=True,
        snapshot_source=None,
        name=None,
        name_style="english",
        agent_command=None,
        add_command=(),
        user=None,
        source=None,
        source_agent=None,
        source_host=None,
        source_path=None,
        target=None,
        target_path=None,
        in_place=False,
        copy_source=False,
        clone=False,
        worktree=False,
        rsync=None,
        rsync_args=None,
        include_git=True,
        include_unclean=None,
        include_gitignored=False,
        base_branch=None,
        new_branch="",
        new_branch_prefix="mng/",
        depth=None,
        shallow_since=None,
        agent_env=(),
        agent_env_file=(),
        pass_agent_env=(),
        host=None,
        new_host=None,
        host_name=None,
        host_name_style="astronomy",
        tag=(),
        label=(),
        project=None,
        host_env=(),
        host_env_file=(),
        pass_host_env=(),
        known_hosts=(),
        authorized_keys=(),
        snapshot=None,
        build_arg=(),
        build_args=None,
        start_arg=(),
        start_args=None,
        reconnect=True,
        interactive=None,
        message=None,
        message_file=None,
        edit_message=False,
        resume_message=None,
        resume_message_file=None,
        retry=3,
        retry_delay="5s",
        attach_command=None,
        connect_command=None,
        idle_timeout=None,
        idle_mode=None,
        activity_sources=None,
        start_on_boot=None,
        start_host=True,
        grant=(),
        user_command=(),
        sudo_command=(),
        upload_file=(),
        append_to_file=(),
        prepend_to_file=(),
        create_directory=(),
        ready_timeout=10.0,
        yes=False,
    )


@pytest.fixture
def default_connect_cli_opts() -> ConnectCliOptions:
    """Baseline ConnectCliOptions with sensible defaults for all fields.

    Tests use .model_copy_update() with to_update() to override only the fields
    relevant to each test case.
    """
    return ConnectCliOptions(
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
        agent=None,
        start=True,
        reconnect=True,
        message=None,
        message_file=None,
        ready_timeout=10.0,
        retry=3,
        retry_delay="5s",
        attach_command=None,
        allow_unknown_host=False,
    )


@pytest.fixture
def intercepted_execvp_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Intercept os.execvpe in connect_to_agent and return the captured calls.

    os.execvpe replaces the current process, making it impossible to test
    CLI-level connect flows without interception. This fixture uses pytest
    monkeypatch to replace it with a simple recorder.
    """
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        "imbue.mng.api.connect.os.execvpe",
        lambda program, args, env: calls.append((program, args)),
    )
    return calls


_REPO_ROOT = Path(__file__).resolve().parents[5]
_WORKSPACE_PACKAGES = (
    _REPO_ROOT / "libs" / "imbue_common",
    _REPO_ROOT / "libs" / "concurrency_group",
    _REPO_ROOT / "libs" / "mng",
)


@pytest.fixture
def isolated_mng_venv(tmp_path: Path) -> Path:
    """Create a temporary venv with mng installed for subprocess-based tests.

    Returns the venv directory. Use `venv / "bin" / "mng"` to run mng
    commands, or `venv / "bin" / "python"` for the interpreter.

    This fixture is useful for tests that install/uninstall packages and
    need full isolation from the main workspace venv.
    """
    venv_dir = tmp_path / "isolated-venv"

    install_args: list[str] = []
    for pkg in _WORKSPACE_PACKAGES:
        install_args.extend(["-e", str(pkg)])

    cg = ConcurrencyGroup(name="isolated-venv-setup")
    with cg:
        cg.run_process_to_completion(("uv", "venv", str(venv_dir)))
        cg.run_process_to_completion(
            ("uv", "pip", "install", "--python", str(venv_dir / "bin" / "python"), *install_args)
        )

    return venv_dir


def _create_and_track_test_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mng_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
    created_sessions: list[str],
    agent_name: str,
    agent_cmd: str = "sleep 482917",
) -> str:
    """Create a test agent via CLI and track its session for cleanup."""
    session_name = create_test_agent_via_cli(
        cli_runner, temp_work_dir, mng_test_prefix, plugin_manager, agent_name, agent_cmd
    )
    created_sessions.append(session_name)
    return session_name


@pytest.fixture
def create_test_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mng_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> Generator[Callable[..., str], None, None]:
    """Factory fixture that creates test agents via CLI and cleans up automatically.

    Usage:
        def test_something(create_test_agent):
            session_name = create_test_agent("my-agent")
            # ... test logic ...
            # cleanup happens automatically on fixture teardown

    Supports creating multiple agents per test -- all are cleaned up.
    """
    created_sessions: list[str] = []
    yield lambda agent_name, agent_cmd="sleep 482917": _create_and_track_test_agent(
        cli_runner, temp_work_dir, mng_test_prefix, plugin_manager, created_sessions, agent_name, agent_cmd
    )

    for session_name in created_sessions:
        cleanup_tmux_session(session_name)
