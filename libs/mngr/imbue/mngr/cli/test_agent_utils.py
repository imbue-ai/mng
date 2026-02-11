"""Integration tests for agent_utils -- select_agent_interactively_with_host.

These tests create a real agent via the CLI, then exercise
select_agent_interactively_with_host end-to-end. The only thing
monkeypatched is the urwid TUI (select_agent_interactively), since it
requires an interactive terminal. Everything else -- list_agents,
load_all_agents_grouped_by_host, find_and_maybe_start_agent_by_name_or_id --
runs against real data on disk.
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mngr.cli.agent_utils import select_agent_interactively_with_host
from imbue.mngr.cli.create import create
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentName
from imbue.mngr.utils.testing import cleanup_tmux_session


@contextmanager
def _created_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
    agent_name: str,
    sleep_id: int,
) -> Generator[str, None, None]:
    """Create an agent and clean it up on exit. Yields the session name."""
    session_name = f"{mngr_test_prefix}{agent_name}"
    try:
        create_result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                f"sleep {sleep_id}",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0, f"Create failed with: {create_result.output}"
        yield session_name
    finally:
        cleanup_tmux_session(session_name)


def test_select_agent_interactively_with_host_returns_selected_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a real agent, returns the (AgentInterface, OnlineHostInterface) tuple."""
    agent_name = f"test-select-agent-{int(time.time())}"

    with _created_agent(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name, 564738):
        # Monkeypatch only the TUI -- return the first agent from the list.
        monkeypatch.setattr(
            "imbue.mngr.cli.agent_utils.select_agent_interactively",
            lambda agents: agents[0],
        )

        result = select_agent_interactively_with_host(temp_mngr_ctx)

        assert result is not None
        agent, host = result
        assert isinstance(agent, AgentInterface)
        assert isinstance(host, OnlineHostInterface)
        assert agent.name == AgentName(agent_name)


def test_select_agent_interactively_with_host_returns_none_when_user_quits(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
    temp_mngr_ctx: MngrContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a real agent present, returns None when the TUI returns None (user quit)."""
    agent_name = f"test-select-quit-{int(time.time())}"

    with _created_agent(cli_runner, temp_work_dir, mngr_test_prefix, plugin_manager, agent_name, 564739):
        monkeypatch.setattr(
            "imbue.mngr.cli.agent_utils.select_agent_interactively",
            lambda agents: None,
        )

        result = select_agent_interactively_with_host(temp_mngr_ctx)

        assert result is None
