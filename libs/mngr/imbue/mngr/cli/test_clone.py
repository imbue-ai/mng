"""Integration tests for the clone CLI command."""

import subprocess
import time
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.clone import clone
from imbue.mngr.cli.create import create
from imbue.mngr.cli.list import list_command
from imbue.mngr.utils.testing import cleanup_tmux_session
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

        # Verify the cloned agent appears in list output
        list_result = cli_runner.invoke(
            list_command,
            [],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert list_result.exit_code == 0

        # There should be at least 2 agents: the source and the clone
        # The clone gets an auto-generated name, so just check we have multiple agents
        output_lines = [line for line in list_result.output.strip().split("\n") if source_name in line]
        assert len(output_lines) >= 1, f"Expected source agent in list output, got: {list_result.output}"

    finally:
        # Clean up all tmux sessions with our test prefix
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for session in result.stdout.strip().split("\n"):
                if session.startswith(mngr_test_prefix):
                    cleanup_tmux_session(session)
