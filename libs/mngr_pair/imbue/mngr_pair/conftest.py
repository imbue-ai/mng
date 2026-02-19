import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pluggy
import pytest
from click.testing import CliRunner

import imbue.mngr.main
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.agents.agent_registry import load_agents_from_plugins
from imbue.mngr.agents.agent_registry import reset_agent_registry
from imbue.mngr.plugins import hookspecs
from imbue.mngr.providers.registry import load_local_backend_only
from imbue.mngr.providers.registry import reset_backend_registry
from imbue.mngr.utils.testing import assert_home_is_temp_directory
from imbue.mngr.utils.testing import init_git_repo


@pytest.fixture
def cg() -> Generator[ConcurrencyGroup, None, None]:
    """Provide a ConcurrencyGroup for tests that need to run processes."""
    with ConcurrencyGroup(name="test") as group:
        yield group


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner for testing CLI commands."""
    return CliRunner()


@pytest.fixture(autouse=True)
def plugin_manager() -> Generator[pluggy.PluginManager, None, None]:
    """Create a plugin manager with mngr hookspecs and local backend only.

    Also loads external plugins via setuptools entry points to match the behavior
    of load_config(). This ensures that external plugins like mngr_pair are
    discovered and registered.

    This fixture also resets the module-level plugin manager singleton to ensure
    test isolation.
    """
    imbue.mngr.main.reset_plugin_manager()
    reset_backend_registry()
    reset_agent_registry()

    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("mngr")
    load_local_backend_only(pm)
    load_agents_from_plugins(pm)

    yield pm

    imbue.mngr.main.reset_plugin_manager()
    reset_backend_registry()
    reset_agent_registry()


@pytest.fixture
def temp_host_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for host/mngr data."""
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir()
    return host_dir


@pytest.fixture
def _isolate_tmux_server(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Give each test its own isolated tmux server."""
    tmux_tmpdir = Path(tempfile.mkdtemp(prefix="mngr-tmux-", dir="/tmp"))
    monkeypatch.setenv("TMUX_TMPDIR", str(tmux_tmpdir))
    monkeypatch.delenv("TMUX", raising=False)

    yield

    tmux_tmpdir_str = str(tmux_tmpdir)
    assert tmux_tmpdir_str.startswith("/tmp/mngr-tmux-"), (
        f"TMUX_TMPDIR safety check failed! Expected /tmp/mngr-tmux-* path but got: {tmux_tmpdir_str}. "
        "Refusing to run 'tmux kill-server' to avoid killing the real tmux server."
    )
    socket_path = Path(tmux_tmpdir_str) / f"tmux-{os.getuid()}" / "default"
    kill_env = os.environ.copy()
    kill_env.pop("TMUX", None)
    kill_env["TMUX_TMPDIR"] = tmux_tmpdir_str
    subprocess.run(
        ["tmux", "-S", str(socket_path), "kill-server"],
        capture_output=True,
        env=kill_env,
    )
    shutil.rmtree(tmux_tmpdir, ignore_errors=True)


@pytest.fixture(autouse=True)
def setup_test_mngr_env(
    tmp_path: Path,
    temp_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolate_tmux_server: None,
) -> Generator[None, None, None]:
    """Set up environment variables for all tests."""
    mngr_test_id = uuid4().hex
    mngr_test_prefix = f"mngr_{mngr_test_id}-"
    mngr_test_root_name = f"mngr-test-{mngr_test_id}"

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MNGR_HOST_DIR", str(temp_host_dir))
    monkeypatch.setenv("MNGR_PREFIX", mngr_test_prefix)
    monkeypatch.setenv("MNGR_ROOT_NAME", mngr_test_root_name)

    unison_dir = tmp_path / ".unison"
    unison_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("UNISON", str(unison_dir))

    assert_home_is_temp_directory()

    yield


@pytest.fixture
def setup_git_config(tmp_path: Path) -> None:
    """Create a .gitconfig in the fake HOME so git commands work."""
    gitconfig = tmp_path / ".gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text("[user]\n\tname = Test User\n\temail = test@test.com\n")


@pytest.fixture
def temp_git_repo(tmp_path: Path, setup_git_config: None) -> Path:
    """Create a temporary git repository with an initial commit."""
    repo_dir = tmp_path / "git_repo"
    repo_dir.mkdir()
    init_git_repo(repo_dir)
    return repo_dir
