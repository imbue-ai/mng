"""Integration and release tests for the Claude agent.

Integration tests verify dialog detection during send_message using tmux.
Release tests require Modal credentials and are marked with @pytest.mark.release.

To run release tests locally:

    PYTEST_MAX_DURATION=600 uv run pytest --no-cov --cov-fail-under=0 -n 0 -m release \\
        libs/mng/imbue/mng/agents/default_plugins/test_claude_agent.py::test_claude_agent_provisioning_on_modal
"""

import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from imbue.mng.agents.default_plugins.claude_agent_test import make_claude_agent
from imbue.mng.config.data_types import MngContext
from imbue.mng.conftest import ModalSubprocessTestEnv
from imbue.mng.errors import DialogDetectedError
from imbue.mng.errors import SendMessageError
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.utils.polling import wait_for
from imbue.mng.utils.testing import cleanup_tmux_session

_SHORT_TIMEOUT = 0.5


def _short_send_message_timeouts():
    """Shorten send_message timeouts for tests without a real agent process."""
    return (
        patch("imbue.mng.agents.base_agent._SEND_MESSAGE_TIMEOUT_SECONDS", _SHORT_TIMEOUT),
        patch("imbue.mng.agents.base_agent._ENTER_SUBMISSION_WAIT_FOR_TIMEOUT_SECONDS", _SHORT_TIMEOUT),
    )


# =============================================================================
# Dialog Detection Integration Tests
# =============================================================================


def test_send_message_raises_dialog_detected_when_dialog_visible(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mng_ctx: MngContext
) -> None:
    """send_message should raise DialogDetectedError when a dialog is blocking the pane."""
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mng_ctx)
    session_name = agent.session_name

    agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'echo \"Do you want to proceed?\"; sleep 847601'",
        timeout_seconds=5.0,
    )

    try:
        wait_for(
            lambda: agent._check_pane_contains(session_name, "Do you want to proceed?"),
            timeout=5.0,
            error_message="Dialog text not visible in pane",
        )

        with pytest.raises(DialogDetectedError, match="permission dialog"):
            agent.send_message("hello")
    finally:
        cleanup_tmux_session(session_name)


def test_send_message_does_not_raise_dialog_detected_when_no_dialog(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mng_ctx: MngContext
) -> None:
    """send_message should not raise DialogDetectedError when no dialog is present.

    The send will fail for other reasons (no real Claude Code process), but
    the important thing is that it gets past the dialog check.
    """
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mng_ctx)
    session_name = agent.session_name

    agent.host.execute_command(
        f"tmux new-session -d -s '{session_name}' 'echo \"Normal output here\"; sleep 847602'",
        timeout_seconds=5.0,
    )

    try:
        wait_for(
            lambda: agent._check_pane_contains(session_name, "Normal output here"),
            timeout=5.0,
            error_message="Content not visible in pane",
        )

        # Should NOT raise DialogDetectedError. Will raise SendMessageError
        # because there's no real Claude Code process to handle the input.
        p1, p2 = _short_send_message_timeouts()
        with p1, p2, pytest.raises(SendMessageError) as exc_info:
            agent.send_message("hello")
        assert not isinstance(exc_info.value, DialogDetectedError)
    finally:
        cleanup_tmux_session(session_name)


# =============================================================================
# Release Tests
# =============================================================================


@pytest.fixture
def temp_source_dir(tmp_path: Path) -> Path:
    """Create a temporary source directory for tests."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    # Create a simple file so the directory isn't empty
    (source_dir / "test.txt").write_text("test content")
    return source_dir


@pytest.mark.release
@pytest.mark.timeout(600)
def test_claude_agent_provisioning_on_modal(
    temp_source_dir: Path,
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test creating a claude agent on Modal.

    This is an end-to-end release test that verifies:
    1. Claude agent can be provisioned on Modal
    2. Claude credentials are transferred correctly (if available locally)
    3. Claude is installed on the remote host
    4. The agent is created and started successfully

    The test uses --dangerously-skip-permissions -p "just say 'hello'" to run
    a quick, non-interactive claude session. The actual output goes to tmux,
    so we only verify that the agent was created successfully.
    """
    # Use a unique agent name with globally unique id to avoid collisions
    unique_id = uuid4().hex[:12]
    agent_name = f"test-claude-modal-{unique_id}"

    # make a .gitignore file to ignore the claude local settings
    claude_settings_dir = temp_source_dir / ".claude"
    claude_settings_dir.mkdir()
    (claude_settings_dir / "settings.local.json").write_text("{}")
    (temp_source_dir / ".gitignore").write_text(".claude/settings.local.json\n")

    # Run mng create with claude agent on modal
    # Using --no-connect and --await-ready to run synchronously without attaching
    # Using --no-ensure-clean since temp dir won't be a git repo
    result = subprocess.run(
        [
            "uv",
            "run",
            "mng",
            "create",
            agent_name,
            "claude",
            "--in",
            "modal",
            "--no-connect",
            "--await-ready",
            "--no-ensure-clean",
            "--source",
            str(temp_source_dir),
            "--",
            "--dangerously-skip-permissions",
            "-p",
            "just say 'hello'",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env=modal_subprocess_env.env,
    )

    # Check that the command succeeded
    assert result.returncode == 0, f"CLI failed with stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "Done." in result.stdout, f"Expected 'Done.' in output: {result.stdout}"

    # Verify that Claude was installed (this message appears in the provisioning output)
    # This confirms that the claude plugin provisioning hook ran correctly
    combined_output = result.stdout + result.stderr
    assert "Claude installed successfully" in combined_output or "Claude is already installed" in combined_output, (
        f"Expected Claude installation message in output.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
