"""Acceptance tests for the message command and message sending functionality.

These tests verify that `mngr create --message` and `mngr message` work correctly
with real Claude Code agents. They are marked with @pytest.mark.acceptance and
require network access to run.

Run with:
    pytest -m acceptance libs/mngr/imbue/mngr/cli/test_message.py --timeout=300
"""

import subprocess
import time
from collections.abc import Generator

import pytest

from imbue.mngr.utils.testing import get_short_random_string


def run_mngr(*args: str, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    """Run mngr command and return the result."""
    return subprocess.run(
        ["uv", "run", "mngr", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@pytest.fixture
def claude_agent() -> Generator[str, None, None]:
    """Create a Claude agent for testing and clean it up after."""
    agent_name = f"test-msg-{get_short_random_string()}"

    # Create agent without message, wait for it to be ready
    result = run_mngr(
        "create",
        agent_name,
        "--agent-type",
        "claude",
        "--no-connect",
        "--no-ensure-clean",
        "--await-ready",
    )
    if result.returncode != 0:
        pytest.fail(f"Failed to create agent: {result.stderr}")

    # Wait a bit for Claude to fully initialize
    time.sleep(2)

    yield agent_name

    # Cleanup
    run_mngr("destroy", agent_name, "--force")


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_message_succeeds() -> None:
    """Test that `mngr create --message` successfully sends a message to Claude.

    This tests the integrated flow where the message is sent as part of agent creation.
    """
    agent_name = f"test-create-msg-{get_short_random_string()}"
    message = f"test message {get_short_random_string()}"

    try:
        result = run_mngr(
            "create",
            agent_name,
            "--agent-type",
            "claude",
            "--message",
            message,
            "--no-connect",
            "--no-ensure-clean",
            "-v",
        )

        # Check that the command succeeded
        assert result.returncode == 0, f"mngr create failed: {result.stderr}"

        # Check for successful submission in verbose output
        assert (
            "Message submitted successfully" in result.stderr or "Message submitted successfully" in result.stdout
        ), f"Message submission not confirmed in output:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    finally:
        # Cleanup
        run_mngr("destroy", agent_name, "--force")


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_message_to_existing_agent_succeeds(claude_agent: str) -> None:
    """Test that `mngr message` successfully sends a message to an existing agent.

    This tests the separate flow where an agent is created first, then messaged separately.
    """
    message = f"test message {get_short_random_string()}"

    result = run_mngr(
        "message",
        claude_agent,
        "-m",
        message,
        "-v",
    )

    # Check that the command succeeded
    assert result.returncode == 0, f"mngr message failed: {result.stderr}"

    # Check for successful submission in verbose output
    assert "Message submitted successfully" in result.stderr or "Message submitted successfully" in result.stdout, (
        f"Message submission not confirmed in output:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_create_with_message_multiple_times() -> None:
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
            result = run_mngr(
                "create",
                agent_name,
                "--agent-type",
                "claude",
                "--message",
                message,
                "--no-connect",
                "--no-ensure-clean",
                "-v",
            )

            if result.returncode == 0 and "Message submitted successfully" in (result.stderr + result.stdout):
                successes += 1
            else:
                failures.append(f"Trial {i}: returncode={result.returncode}, stderr={result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            failures.append(f"Trial {i}: timeout")
        finally:
            run_mngr("destroy", agent_name, "--force")

    # Require 100% success rate
    assert successes == trial_count, (
        f"Message reliability test failed: {successes}/{trial_count} succeeded\nFailures: {failures}"
    )


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_mngr_message_multiple_times(claude_agent: str) -> None:
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
            result = run_mngr(
                "message",
                claude_agent,
                "-m",
                message,
                "-v",
            )

            if result.returncode == 0 and "Message submitted successfully" in (result.stderr + result.stdout):
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
