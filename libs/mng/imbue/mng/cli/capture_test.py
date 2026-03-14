"""Unit tests for the capture CLI command."""

import subprocess
from collections.abc import Callable

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mng.cli.capture import capture
from imbue.mng.utils.polling import wait_for


def test_capture_no_agent_headless_fails(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Capture with no agent in headless mode should fail with a clear error."""
    result = cli_runner.invoke(
        capture,
        ["--headless"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "No agent specified" in result.output


def _tmux_pane_contains(session_name: str, marker: str) -> bool:
    """Check if the tmux pane content contains the marker string."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session_name, "-p"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0 and marker in result.stdout


@pytest.mark.tmux
def test_capture_outputs_pane_content(
    cli_runner: CliRunner,
    create_test_agent: Callable[..., str],
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Capture command should output the visible pane content for a running agent."""
    agent_name = "test-capture-visible"
    session_name = create_test_agent(agent_name, "echo CAPTURE_TEST_MARKER && sleep 493827")

    wait_for(
        lambda: _tmux_pane_contains(session_name, "CAPTURE_TEST_MARKER"),
        timeout=5.0,
        error_message="Echo output did not appear in tmux pane",
    )

    result = cli_runner.invoke(
        capture,
        [agent_name],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "CAPTURE_TEST_MARKER" in result.output


@pytest.mark.tmux
def test_capture_full_scrollback(
    cli_runner: CliRunner,
    create_test_agent: Callable[..., str],
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Capture --full should include scrollback buffer content."""
    agent_name = "test-capture-full"
    session_name = create_test_agent(agent_name, "echo SCROLLBACK_MARKER && sleep 493827")

    wait_for(
        lambda: _tmux_pane_contains(session_name, "SCROLLBACK_MARKER"),
        timeout=5.0,
        error_message="Echo output did not appear in tmux pane",
    )

    result = cli_runner.invoke(
        capture,
        [agent_name, "--full"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "SCROLLBACK_MARKER" in result.output
