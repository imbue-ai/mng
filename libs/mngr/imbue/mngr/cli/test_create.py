"""Tests for the create CLI command."""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.create import create
from imbue.mngr.main import cli
from imbue.mngr.utils.testing import capture_tmux_pane_contents
from imbue.mngr.utils.testing import tmux_session_cleanup
from imbue.mngr.utils.testing import tmux_session_exists
from imbue.mngr.utils.testing import wait_for


def test_cli_create_with_echo_command(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    temp_host_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test creating an agent with a simple echo command."""
    agent_name = f"test-cli-echo-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "echo 'hello from cli test' && sleep 958374",
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

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert "Created agent:" in result.output
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        agents_dir = temp_host_dir / "agents"
        assert agents_dir.exists(), "agents directory should exist in temp dir"


def test_cli_create_via_cli_group(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
) -> None:
    """Test calling create through the main CLI group."""
    agent_name = f"test-cli-group-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            cli,
            [
                "create",
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 482913",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"


def test_cli_create_via_subprocess(
    temp_work_dir: Path,
    temp_host_dir: Path,
    mngr_test_prefix: str,
) -> None:
    """Test calling the mngr create command via subprocess."""
    agent_name = f"test-subprocess-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"
    env = os.environ.copy()
    # Pass the test environment variables to the subprocess for proper isolation
    env["MNGR_HOST_DIR"] = str(temp_host_dir)
    env["MNGR_PREFIX"] = mngr_test_prefix

    with tmux_session_cleanup(session_name):
        result = subprocess.run(
            [
                "uv",
                "run",
                "mngr",
                "create",
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 651472",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
                # Disable modal to avoid auth errors in CI
                "--disable-plugin",
                "modal",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        agents_dir = temp_host_dir / "agents"
        assert agents_dir.exists(), "agents directory should exist in temp dir"


def test_connect_flag_calls_tmux_attach_for_local_agent(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --connect flag attempts to attach to the tmux session for local agents."""
    agent_name = f"test-connect-local-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        with patch("os.execvp") as mock_execvp:
            cli_runner.invoke(
                create,
                [
                    "--name",
                    agent_name,
                    "--agent-cmd",
                    "sleep 397265",
                    "--source",
                    str(temp_work_dir),
                    "--connect",
                    "--no-copy-work-dir",
                    "--no-ensure-clean",
                ],
                obj=plugin_manager,
                catch_exceptions=False,
            )
            mock_execvp.assert_called_once_with("tmux", ["tmux", "attach", "-t", session_name])


def test_no_connect_flag_skips_tmux_attach(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --no-connect flag skips attaching to the tmux session."""
    agent_name = f"test-no-connect-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        with patch("os.execvp") as mock_execvp:
            result = cli_runner.invoke(
                create,
                [
                    "--name",
                    agent_name,
                    "--agent-cmd",
                    "sleep 529847",
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

            assert result.exit_code == 0, f"CLI failed with: {result.output}"
            mock_execvp.assert_not_called()
            assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"


def test_message_file_flag_reads_message_from_file(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    tmp_path: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --message-file reads the initial message from a file."""
    agent_name = f"test-message-file-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    message_file = tmp_path / "message.txt"
    message_content = "Hello from file"
    message_file.write_text(message_content)

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "cat",
                "--message-file",
                str(message_file),
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

        assert result.exit_code == 0, f"CLI failed with: {result.output}"

        wait_for(
            lambda: tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to exist",
        )

        wait_for(
            lambda: message_content in capture_tmux_pane_contents(session_name),
            error_message=f"Expected message '{message_content}' to appear in tmux pane output",
        )


def test_message_and_message_file_both_provided_raises_error(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that providing both --message and --message-file raises an error."""
    agent_name = f"test-both-message-{int(time.time())}"

    message_file = tmp_path / "message.txt"
    message_file.write_text("Hello from file")

    result = cli_runner.invoke(
        create,
        [
            "--name",
            agent_name,
            "--agent-cmd",
            "cat",
            "--message",
            "Hello from flag",
            "--message-file",
            str(message_file),
            "--source",
            str(temp_work_dir),
            "--no-connect",
            "--no-copy-work-dir",
            "--no-ensure-clean",
        ],
        obj=plugin_manager,
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert "Cannot provide both --message and --message-file" in str(result.exception)


def test_multiline_message_creates_file_and_pipes(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    tmp_path: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that multi-line messages are sent using tmux send-keys."""
    agent_name = f"test-multiline-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    message_file = tmp_path / "multiline.txt"
    multiline_message = "Line 1\nLine 2\nLine 3"
    message_file.write_text(multiline_message)

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "cat",
                "--message-file",
                str(message_file),
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

        assert result.exit_code == 0, f"CLI failed with: {result.output}"

        wait_for(
            lambda: tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to exist",
        )

        for line in ["Line 1", "Line 2", "Line 3"]:
            wait_for(
                lambda line=line: line in capture_tmux_pane_contents(session_name),
                error_message=f"Expected line '{line}' to appear in tmux pane output",
            )


def test_single_line_message_uses_echo(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that single-line messages are sent using tmux send-keys."""
    agent_name = f"test-single-line-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"
    single_line_message = "Hello single line"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "cat",
                "--message",
                single_line_message,
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

        assert result.exit_code == 0, f"CLI failed with: {result.output}"

        wait_for(
            lambda: tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to exist",
        )

        wait_for(
            lambda: single_line_message in capture_tmux_pane_contents(session_name),
            error_message=f"Expected message '{single_line_message}' to appear in tmux pane output",
        )


def test_no_await_ready_creates_agent_in_background(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --no-await-ready creates agent in background and exits immediately."""
    agent_name = f"test-no-await-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 817364",
                "--source",
                str(temp_work_dir),
                "--no-connect",
                "--no-await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert "Agent creation started in background" in result.output
        assert agent_name in result.output

        wait_for(
            lambda: tmux_session_exists(session_name),
            error_message=f"Expected tmux session {session_name} to exist",
        )


def test_add_command_with_named_window(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that -c with name=command syntax creates a tmux window with the specified name."""
    agent_name = f"test-named-window-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 629481",
                "-c",
                'myserver="sleep 847192"',
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

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        window_list_result = subprocess.run(
            ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
        )
        window_names = window_list_result.stdout.strip().split("\n")
        assert "myserver" in window_names, f"Expected window 'myserver' in {window_names}"


def test_add_command_without_name_uses_default_window_name(
    cli_runner: CliRunner,
    temp_work_dir: Path,
    mngr_test_prefix: str,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that -c without name prefix creates a tmux window with default name (cmd-N)."""
    agent_name = f"test-default-window-{int(time.time())}"
    session_name = f"{mngr_test_prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 538274",
                "-c",
                "sleep 719283",
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

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert tmux_session_exists(session_name), f"Expected tmux session {session_name} to exist"

        window_list_result = subprocess.run(
            ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
        )
        window_names = window_list_result.stdout.strip().split("\n")
        assert "cmd-1" in window_names, f"Expected window 'cmd-1' in {window_names}"
