"""Acceptance tests for the message command and message sending functionality.

These tests verify that `mngr create --message` and `mngr message` work correctly
with real Claude Code agents. They are marked with @pytest.mark.acceptance and
require network access to run.

Run with:
    pytest -m acceptance libs/mngr/imbue/mngr/cli/test_message.py --timeout=300
"""

import shutil
import subprocess
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from imbue.mngr.utils.git_utils import find_git_common_dir
from imbue.mngr.utils.testing import get_short_random_string
from imbue.mngr.utils.testing import setup_claude_trust_config_for_subprocess


def _is_claude_installed() -> bool:
    """Check if Claude Code CLI is installed and available."""
    return shutil.which("claude") is not None


# Skip all tests in this module if Claude is not installed
pytestmark = pytest.mark.skipif(not _is_claude_installed(), reason="Claude Code CLI is not installed")


@pytest.fixture
def claude_trust_env() -> dict[str, str]:
    """Create a Claude trust config for subprocess tests.

    This fixture creates ~/.claude.json in the temp HOME (set by the autouse
    setup_test_mngr_env fixture) that marks the necessary directories as trusted.

    When running from a worktree, we need to trust the original repo (git common dir)
    because mngr checks if the source directory is trusted before creating worktrees.
    """
    cwd = Path.cwd().resolve()
    paths_to_trust = [cwd]

    # If running from a worktree, also trust the original repo
    git_common_dir = find_git_common_dir(cwd)
    if git_common_dir is not None:
        original_repo = git_common_dir.parent
        if original_repo != cwd:
            paths_to_trust.append(original_repo)

    return setup_claude_trust_config_for_subprocess(paths_to_trust)


def _run_mngr(*args: str, timeout: float = 120, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run mngr command and return the result."""
    return subprocess.run(
        ["uv", "run", "mngr", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _create_agent(
    name: str,
    *,
    message: str | None = None,
    verbose: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Create a Claude agent with standard test flags.

    Uses --pass-env HOME so the tmux session inherits the test's fake HOME
    (tmux sessions inherit the server's HOME, not the client's).
    """
    args = [
        "create",
        name,
        "--agent-type",
        "claude",
        "--no-connect",
        "--no-ensure-clean",
        "--await-ready",
        "--pass-env",
        "HOME",
    ]
    if message is not None:
        args.extend(["--message", message])
    if verbose:
        args.append("-v")
    return _run_mngr(*args, env=env)


def _destroy_agent(name: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Destroy a Claude agent."""
    return _run_mngr("destroy", name, "--force", env=env)


def _send_message(
    agent_name: str, message: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Send a message to an existing Claude agent."""
    return _run_mngr("message", agent_name, "-m", message, "-v", env=env)


def _message_was_submitted(result: subprocess.CompletedProcess[str]) -> bool:
    """Check if the message submission was confirmed in the command output."""
    return "Message submitted successfully" in (result.stderr + result.stdout)


@pytest.fixture
def claude_agent(claude_trust_env: dict[str, str]) -> Generator[str, None, None]:
    """Create a Claude agent for testing and clean it up after."""
    agent_name = f"test-msg-{get_short_random_string()}"

    result = _create_agent(agent_name, env=claude_trust_env)
    if result.returncode != 0:
        pytest.fail(f"Failed to create agent: {result.stderr}")

    # Wait a bit for Claude to fully initialize
    time.sleep(2)

    yield agent_name

    _destroy_agent(agent_name, env=claude_trust_env)


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_message_succeeds(claude_trust_env: dict[str, str]) -> None:
    """Test that `mngr create --message` successfully sends a message to Claude.

    This tests the integrated flow where the message is sent as part of agent creation.
    """
    agent_name = f"test-create-msg-{get_short_random_string()}"
    message = f"test message {get_short_random_string()}"

    try:
        result = _create_agent(agent_name, message=message, verbose=True, env=claude_trust_env)

        assert result.returncode == 0, f"mngr create failed: {result.stderr}"
        assert _message_was_submitted(result), (
            f"Message submission not confirmed in output:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    finally:
        _destroy_agent(agent_name, env=claude_trust_env)


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_message_to_existing_agent_succeeds(claude_agent: str, claude_trust_env: dict[str, str]) -> None:
    """Test that `mngr message` successfully sends a message to an existing agent.

    This tests the separate flow where an agent is created first, then messaged separately.
    """
    message = f"test message {get_short_random_string()}"

    result = _send_message(claude_agent, message, env=claude_trust_env)

    assert result.returncode == 0, f"mngr message failed: {result.stderr}"
    assert _message_was_submitted(result), (
        f"Message submission not confirmed in output:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_message_multiple_times(claude_trust_env: dict[str, str]) -> None:
    """Test that `mngr create --message` works reliably across multiple trials.

    This is a reliability test that creates multiple agents with messages to verify
    the message sending mechanism works consistently.
    """
    trial_count = 5
    successes = 0
    failures: list[str] = []

    for i in range(trial_count):
        agent_name = f"test-multi-{i}-{get_short_random_string()}"
        message = f"test message {i}"

        try:
            result = _create_agent(agent_name, message=message, verbose=True, env=claude_trust_env)

            if result.returncode == 0 and _message_was_submitted(result):
                successes += 1
            else:
                failures.append(f"Trial {i}: returncode={result.returncode}, stderr={result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            failures.append(f"Trial {i}: timeout")
        finally:
            _destroy_agent(agent_name, env=claude_trust_env)

    # Require 100% success rate
    assert successes == trial_count, (
        f"Message reliability test failed: {successes}/{trial_count} succeeded\nFailures: {failures}"
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_message_multiple_times(claude_agent: str, claude_trust_env: dict[str, str]) -> None:
    """Test that `mngr message` works reliably across multiple sends to the same agent.

    This is a reliability test that sends multiple messages to verify the message
    sending mechanism works consistently when the agent is already running.
    """
    trial_count = 5
    successes = 0
    failures: list[str] = []

    for i in range(trial_count):
        message = f"test message {i}"

        try:
            result = _send_message(claude_agent, message, env=claude_trust_env)

            if result.returncode == 0 and _message_was_submitted(result):
                successes += 1
            else:
                failures.append(f"Trial {i}: returncode={result.returncode}, stderr={result.stderr[:200]}")

            # Small delay between messages to let Claude process
            time.sleep(1)
        except subprocess.TimeoutExpired:
            failures.append(f"Trial {i}: timeout")

    # Require 100% success rate
    assert successes == trial_count, (
        f"Message reliability test failed: {successes}/{trial_count} succeeded\nFailures: {failures}"
    )
