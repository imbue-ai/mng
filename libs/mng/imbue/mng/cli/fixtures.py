from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.cli.connect import ConnectCliOptions
from imbue.mng.cli.create import CreateCliOptions
from imbue.mng.interfaces.data_types import AgentInfo
from imbue.mng.interfaces.data_types import HostInfo
from imbue.mng.interfaces.data_types import SnapshotInfo
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import HostId
from imbue.mng.primitives import HostState
from imbue.mng.primitives import ProviderInstanceName


def make_test_agent_info(
    name: str = "test-agent",
    state: AgentLifecycleState = AgentLifecycleState.RUNNING,
    create_time: datetime | None = None,
    snapshots: list[SnapshotInfo] | None = None,
    host_plugin: dict | None = None,
    host_tags: dict[str, str] | None = None,
    labels: dict[str, str] | None = None,
) -> AgentInfo:
    """Create a real AgentInfo for testing.

    Shared helper used across CLI test files to avoid duplicating AgentInfo
    construction logic. Accepts optional overrides for commonly varied fields.
    """
    host_info = HostInfo(
        id=HostId.generate(),
        name="test-host",
        provider_name=ProviderInstanceName("local"),
        snapshots=snapshots or [],
        state=HostState.RUNNING,
        plugin=host_plugin or {},
        tags=host_tags or {},
    )
    return AgentInfo(
        id=AgentId.generate(),
        name=AgentName(name),
        type="generic",
        command=CommandString("sleep 100"),
        work_dir=Path("/tmp/test"),
        create_time=create_time or datetime.now(timezone.utc),
        start_on_boot=False,
        state=state,
        labels=labels or {},
        host=host_info,
    )


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
        known_host=(),
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


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner for testing CLI commands."""
    return CliRunner()


@pytest.fixture
def project_config_dir(temp_git_repo: Path, mng_test_root_name: str) -> Path:
    """Return the project config directory inside the test git repo, creating it.

    The directory is named `.{mng_test_root_name}` (e.g., `.mng-test-abc123`).
    Tests can write `settings.toml` or `settings.local.toml` into this directory
    to configure project-level settings for a test.
    """
    config_dir = temp_git_repo / f".{mng_test_root_name}"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def temp_git_repo_cwd(temp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary git repository and chdir into it.

    Combines temp_git_repo with monkeypatch.chdir so tests that need a git
    repo as the working directory (e.g. for project-scope config discovery)
    don't need to request both fixtures separately.
    """
    monkeypatch.chdir(temp_git_repo)
    return temp_git_repo


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
