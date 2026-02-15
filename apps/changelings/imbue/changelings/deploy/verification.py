# Deployment verification orchestration.
#
# This module handles the impure orchestration of verifying a changeling
# deployment by invoking the function, streaming logs, polling for the agent,
# and cleaning up. All pure helper functions live in deploy.py.
#
# This module is excluded from unit test coverage because it requires real
# Modal and mngr infrastructure to execute (similar to cron_runner.py).
# It is exercised by the release test in test_deploy_modal.py.

import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from loguru import logger

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import AGENT_POLL_INTERVAL_SECONDS
from imbue.changelings.deploy.deploy import AGENT_POLL_TIMEOUT_SECONDS
from imbue.changelings.deploy.deploy import build_modal_run_command
from imbue.changelings.deploy.deploy import parse_agent_name_from_list_json
from imbue.changelings.errors import ChangelingDeployError
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


def _find_changeling_agent(changeling_name: str) -> str | None:
    """Search mngr list for a running agent created by the given changeling.

    Returns the agent name if found, None otherwise.
    """
    with ConcurrencyGroup(name=f"find-agent-{changeling_name}") as cg:
        result = cg.run_process_to_completion(
            ["uv", "run", "mngr", "list", "--format", "json"],
            is_checked_after=False,
            timeout=30.0,
        )

    if result.returncode != 0:
        logger.debug("mngr list failed: {}", result.stderr)
        return None

    agent_name = parse_agent_name_from_list_json(result.stdout, changeling_name)
    if agent_name is not None:
        logger.debug("Found changeling agent: {}", agent_name)
    return agent_name


def _destroy_agent(agent_name: str) -> None:
    """Destroy an agent by name (no-op if it doesn't exist, since --force is used)."""
    logger.info("Destroying agent '{}'", agent_name)
    _run_mngr_command(["uv", "run", "mngr", "destroy", "--force", agent_name])


def _run_mngr_command(cmd: list[str]) -> None:
    """Run an mngr command, logging the result."""
    logger.info("Running: {}", " ".join(cmd))
    with ConcurrencyGroup(name="mngr-cmd") as cg:
        result = cg.run_process_to_completion(cmd, is_checked_after=False, timeout=60.0)

    if result.returncode != 0:
        logger.warning("Command failed (exit {}): {}", result.returncode, result.stderr)


def _stream_process_output(
    process: subprocess.Popen[str],
    error_event: threading.Event,
    error_lines: list[str],
) -> None:
    """Read process stdout line by line, forwarding to console and flagging errors."""
    assert process.stdout is not None
    for line in process.stdout:
        # Write directly to stdout for immediate visibility
        sys.stdout.write(line)
        sys.stdout.flush()

        stripped = line.rstrip()
        lower = stripped.lower()
        if "traceback" in lower or "exception" in lower:
            error_lines.append(stripped)
            error_event.set()


def _poll_for_agent(
    changeling_name: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    error_event: threading.Event,
    process: subprocess.Popen[str],
) -> str | None:
    """Poll mngr list until an agent created by the changeling is found.

    Returns the agent name if found within the timeout, None otherwise.
    Returns None early if the modal run process exits or an error is detected.
    """
    deadline = time.monotonic() + timeout_seconds
    logger.info(
        "Polling for changeling agent '{}' (timeout: {}s, interval: {}s)",
        changeling_name,
        timeout_seconds,
        poll_interval_seconds,
    )

    while time.monotonic() < deadline:
        # Check if the modal run process has exited unexpectedly
        if process.poll() is not None:
            logger.warning("modal run process exited with code {} before agent was detected", process.returncode)
            return None

        # Fail immediately if an error (traceback/exception) is detected in the output
        if error_event.is_set():
            return None

        agent_name = _find_changeling_agent(changeling_name)
        if agent_name is not None:
            logger.info("Detected changeling agent: {}", agent_name)
            return agent_name

        logger.debug("Agent not found yet, waiting {}s before next poll...", poll_interval_seconds)
        time.sleep(poll_interval_seconds)

    return None


def verify_deployment(
    changeling: ChangelingDefinition,
    environment_name: str | None,
    is_finish_initial_run: bool,
    env: Mapping[str, str],
    cron_runner_path: Path,
    agent_poll_timeout_seconds: float = AGENT_POLL_TIMEOUT_SECONDS,
    agent_poll_interval_seconds: float = AGENT_POLL_INTERVAL_SECONDS,
) -> None:
    """Verify deployment by invoking the function and checking agent creation.

    After modal deploy, this function:
    1. Runs `modal run` to invoke the deployed function
    2. Streams logs from the modal run process
    3. Polls `mngr list` for the changeling agent to appear
    4. Once detected, destroys or stops the agent depending on is_finish_initial_run
    5. Raises ChangelingDeployError if an error is detected or agent fails to start
    """
    cmd = build_modal_run_command(cron_runner_path, environment_name)
    logger.info("Invoking deployed function to verify deployment: {}", " ".join(cmd))

    # Start modal run as a subprocess with output streaming
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=dict(env),
    )

    error_event = threading.Event()
    error_lines: list[str] = []
    log_thread = threading.Thread(
        target=_stream_process_output,
        args=(process, error_event, error_lines),
        daemon=True,
    )
    log_thread.start()

    try:
        changeling_name = str(changeling.name)

        # Poll for the agent
        agent_name = _poll_for_agent(
            changeling_name=changeling_name,
            timeout_seconds=agent_poll_timeout_seconds,
            poll_interval_seconds=agent_poll_interval_seconds,
            error_event=error_event,
            process=process,
        )

        # If error detected, clean up and fail
        if error_event.is_set():
            if agent_name is not None:
                _destroy_agent(agent_name)
            process.kill()
            process.wait()
            error_detail = "\n".join(error_lines) if error_lines else "See output above"
            raise ChangelingDeployError(
                f"Error detected during deployment verification of '{changeling_name}':\n{error_detail}"
            )

        if agent_name is None:
            # Agent was not found within timeout (no error detected either)
            process.kill()
            process.wait()
            raise ChangelingDeployError(
                f"Changeling '{changeling_name}' agent failed to start within "
                f"{agent_poll_timeout_seconds}s. Check the logs above for errors."
            )

        if is_finish_initial_run:
            # Let the agent finish its initial run, then stop it
            logger.info("Waiting for agent '{}' to complete its initial run...", agent_name)
            process.wait()
            exit_code = process.returncode
            logger.info("modal run exited with code {}", exit_code)
            # Stop the agent (graceful shutdown, preserves host for inspection)
            _run_mngr_command(["uv", "run", "mngr", "stop", agent_name])
        else:
            # Destroy the agent immediately (we've verified it started)
            _destroy_agent(agent_name)
            # Wait for modal run to exit (it will exit because we killed the agent)
            process.wait(timeout=60)

        logger.info("Deployment verification complete for changeling '{}'", changeling_name)

    except Exception:
        # Make sure we don't leave the process running on any error
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
