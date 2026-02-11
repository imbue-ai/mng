"""Integration tests for the clone CLI command."""

import json
import time
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.clone import clone
from imbue.mngr.cli.create import create
from imbue.mngr.cli.list import list_command
from imbue.mngr.utils.testing import cleanup_tmux_session
from imbue.mngr.utils.testing import tmux_session_cleanup
from imbue.mngr.utils.testing import tmux_session_exists


def test_clone_creates_agent_from_source(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that clone creates a new agent by delegating to create --from-agent."""
    source_name = f"test-clone-source-{int(time.time())}"
    source_session = f"{mngr_test_prefix}{source_name}"
    clone_sessions: list[str] = []

    with tmux_session_cleanup(source_session):
        try:
            # Create a source agent
            create_result = cli_runner.invoke(
                create,
                [
                    "--name",
                    source_name,
                    "--agent-cmd",
                    "sleep 482917",
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
            assert create_result.exit_code == 0, f"Create source failed with: {create_result.output}"
            assert tmux_session_exists(source_session), f"Expected source session {source_session} to exist"

            # Clone the source agent
            clone_result = cli_runner.invoke(
                clone,
                [
                    source_name,
                    "--no-connect",
                    "--await-ready",
                    "--no-copy-work-dir",
                ],
                obj=plugin_manager,
                catch_exceptions=False,
            )
            assert clone_result.exit_code == 0, f"Clone failed with: {clone_result.output}"

            # Use JSON list to find the clone agent and verify it was created
            list_result = cli_runner.invoke(
                list_command,
                ["--format", "json"],
                obj=plugin_manager,
                catch_exceptions=False,
            )
            assert list_result.exit_code == 0

            agents = json.loads(list_result.output)["agents"]
            agent_names = [a["name"] for a in agents]

            # Track clone sessions for cleanup
            clone_sessions = [f"{mngr_test_prefix}{name}" for name in agent_names if name != source_name]

            assert source_name in agent_names, f"Expected source agent in list output, got: {agent_names}"
            assert len(clone_sessions) >= 1, f"Expected at least one clone agent, got agents: {agent_names}"
        finally:
            for session in clone_sessions:
                cleanup_tmux_session(session)
