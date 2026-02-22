"""Shared test fixtures for mng plugin libraries.

This module provides common pytest fixtures that plugin libraries (mng_pair,
mng_schedule, etc.) need for their tests. Instead of duplicating fixture code
in each plugin's conftest.py, plugins can import and re-export these fixtures.

Usage in a plugin's conftest.py:

    from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures
    register_plugin_test_fixtures(globals())

This registers all common fixtures (cli_runner, plugin_manager, temp_host_dir,
_isolate_tmux_server, setup_test_mng_env) into the calling module's namespace,
making them available to pytest.
"""

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

import imbue.mng.main
from imbue.mng.agents.agent_registry import load_agents_from_plugins
from imbue.mng.agents.agent_registry import reset_agent_registry
from imbue.mng.plugins import hookspecs
from imbue.mng.providers.registry import load_local_backend_only
from imbue.mng.providers.registry import reset_backend_registry
from imbue.mng.utils.testing import assert_home_is_temp_directory


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI runner for testing CLI commands."""
    return CliRunner()


@pytest.fixture(autouse=True)
def plugin_manager() -> Generator[pluggy.PluginManager, None, None]:
    """Create a plugin manager with mng hookspecs and local backend only.

    Also loads external plugins via setuptools entry points to match the behavior
    of load_config(). This ensures that external plugins are discovered and registered.

    This fixture also resets the module-level plugin manager singleton to ensure
    test isolation.
    """
    imbue.mng.main.reset_plugin_manager()
    reset_backend_registry()
    reset_agent_registry()

    pm = pluggy.PluginManager("mng")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("mng")
    load_local_backend_only(pm)
    load_agents_from_plugins(pm)

    yield pm

    imbue.mng.main.reset_plugin_manager()
    reset_backend_registry()
    reset_agent_registry()


@pytest.fixture
def temp_host_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for host/mng data."""
    host_dir = tmp_path / ".mng"
    host_dir.mkdir()
    return host_dir


@pytest.fixture(autouse=True)
def _isolate_tmux_server(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Give each test its own isolated tmux server."""
    tmux_tmpdir = Path(tempfile.mkdtemp(prefix="mng-tmux-", dir="/tmp"))
    monkeypatch.setenv("TMUX_TMPDIR", str(tmux_tmpdir))
    monkeypatch.delenv("TMUX", raising=False)

    yield

    tmux_tmpdir_str = str(tmux_tmpdir)
    assert tmux_tmpdir_str.startswith("/tmp/mng-tmux-"), (
        f"TMUX_TMPDIR safety check failed! Expected /tmp/mng-tmux-* path but got: {tmux_tmpdir_str}. "
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
def setup_test_mng_env(
    tmp_path: Path,
    temp_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolate_tmux_server: None,
) -> Generator[None, None, None]:
    """Set up environment variables for all tests."""
    mng_test_id = uuid4().hex
    mng_test_prefix = f"mng_{mng_test_id}-"
    mng_test_root_name = f"mng-test-{mng_test_id}"

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MNG_HOST_DIR", str(temp_host_dir))
    monkeypatch.setenv("MNG_PREFIX", mng_test_prefix)
    monkeypatch.setenv("MNG_ROOT_NAME", mng_test_root_name)

    assert_home_is_temp_directory()

    yield


def register_plugin_test_fixtures(namespace: dict) -> None:
    """Register common plugin test fixtures into the given namespace.

    Call this from a plugin's conftest.py to get the standard set of fixtures
    needed for testing mng plugins:
    - cli_runner: Click CLI test runner
    - plugin_manager: pluggy PluginManager with local backend
    - temp_host_dir: temporary .mng directory
    - _isolate_tmux_server: per-test tmux isolation
    - setup_test_mng_env: environment variable setup
    """
    namespace["cli_runner"] = cli_runner
    namespace["plugin_manager"] = plugin_manager
    namespace["temp_host_dir"] = temp_host_dir
    namespace["_isolate_tmux_server"] = _isolate_tmux_server
    namespace["setup_test_mng_env"] = setup_test_mng_env
