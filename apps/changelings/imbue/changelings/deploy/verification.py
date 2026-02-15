# Deployment verification orchestration.
#
# This module handles the impure orchestration of verifying a changeling
# deployment by invoking the function, streaming logs, and checking for errors.
#
# The verification flow is:
# 1. Run `modal run` to invoke the deployed cron function once.
# 2. Wait for the process to finish (it creates an agent via mngr create
#    with --await-agent-stopped, so it blocks until the agent completes).
# 3. If is_finish_initial_run is True, just check the exit code.
# 4. If is_finish_initial_run is False, destroy the agent after it finishes.
# 5. On timeout or failure, try to destroy any created agent and raise.
#
# This module is excluded from unit test coverage because it requires real
# Modal and mngr infrastructure to execute (similar to cron_runner.py).
# It is exercised by the release test in test_deploy_modal.py.

import re
import subprocess
import sys
import threading
from collections.abc import Mapping
from pathlib import Path

from loguru import logger

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import AGENT_POLL_TIMEOUT_SECONDS
from imbue.changelings.deploy.deploy import build_modal_run_command
from imbue.changelings.errors import ChangelingDeployError
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup

# Regex to extract agent name from mngr create command output.
# The mngr create command logs at -vv level and includes the agent name
# in lines like: "mngr create <agent-name> <agent-type> ..."
_AGENT_NAME_PATTERN = re.compile(r"mngr\s+create\s+(\S+)")


def _destroy_agent(agent_name: str) -> None:
    """Destroy an agent by name (no-op if it doesn't exist, since --force is used)."""
    logger.info("Destroying agent '{}'", agent_name)
    with ConcurrencyGroup(name="mngr-destroy") as cg:
        result = cg.run_process_to_completion(
            ["uv", "run", "mngr", "destroy", "--force", agent_name],
            is_checked_after=False,
            timeout=60.0,
        )
    if result.returncode != 0:
        logger.warning("mngr destroy failed (exit {}): {}", result.returncode, result.stderr)


def _stream_process_output(
    process: subprocess.Popen[str],
    error_event: threading.Event,
    error_lines: list[str],
    # mutable list to capture extracted agent name (thread-safe single write)
    agent_name_holder: list[str],
    changeling_name: str,
) -> None:
    """Read process stdout line by line, forwarding to console and extracting metadata."""
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()

        stripped = line.rstrip()
        lower = stripped.lower()

        # Detect errors (tracebacks/exceptions)
        if "traceback" in lower or "exception" in lower:
            error_lines.append(stripped)
            error_event.set()

        # Extract agent name from mngr create command line in the output.
        # The agent name starts with the changeling name followed by a timestamp.
        if not agent_name_holder and changeling_name in stripped:
            match = _AGENT_NAME_PATTERN.search(stripped)
            if match is not None:
                candidate = match.group(1)
                if candidate.startswith(changeling_name):
                    agent_name_holder.append(candidate)
                    logger.debug("Extracted agent name from output: {}", candidate)


def verify_deployment(
    changeling: ChangelingDefinition,
    environment_name: str | None,
    is_finish_initial_run: bool,
    env: Mapping[str, str],
    cron_runner_path: Path,
    process_timeout_seconds: float = AGENT_POLL_TIMEOUT_SECONDS,
) -> None:
    """Verify deployment by invoking the deployed function and waiting for completion.

    After modal deploy, this function:
    1. Runs `modal run` to invoke the deployed cron function once
    2. Streams output and monitors for errors
    3. Waits for the process to finish (the cron function runs mngr create
       with --await-agent-stopped, so it blocks until the agent completes)
    4. If is_finish_initial_run is False, destroys the agent after it finishes
    5. Raises ChangelingDeployError on timeout, non-zero exit, or detected errors
    """
    changeling_name = str(changeling.name)
    cmd = build_modal_run_command(cron_runner_path, environment_name)
    logger.info("Invoking deployed function to verify deployment: {}", " ".join(cmd))

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
    agent_name_holder: list[str] = []

    log_thread = threading.Thread(
        target=_stream_process_output,
        args=(process, error_event, error_lines, agent_name_holder, changeling_name),
        daemon=True,
    )
    log_thread.start()

    try:
        # Wait for the modal run process to finish. The process runs the full
        # lifecycle: clone repos -> mngr create -> agent runs -> agent stops -> exit.
        exit_code = process.wait(timeout=process_timeout_seconds)
        extracted_agent_name = agent_name_holder[0] if agent_name_holder else None

        # Check for errors
        if error_event.is_set():
            if extracted_agent_name is not None:
                _destroy_agent(extracted_agent_name)
            error_detail = "\n".join(error_lines) if error_lines else "See output above"
            raise ChangelingDeployError(
                f"Error detected during deployment verification of '{changeling_name}':\n{error_detail}"
            )

        if exit_code != 0:
            if extracted_agent_name is not None:
                _destroy_agent(extracted_agent_name)
            raise ChangelingDeployError(
                f"Deployment verification of '{changeling_name}' failed "
                f"(modal run exited with code {exit_code}). See output above for details."
            )

        # Success: the modal run process completed with exit code 0
        logger.info("modal run completed successfully for changeling '{}'", changeling_name)

        if not is_finish_initial_run and extracted_agent_name is not None:
            # Destroy the verification agent (we've confirmed it started and ran successfully)
            _destroy_agent(extracted_agent_name)

        logger.info("Deployment verification complete for changeling '{}'", changeling_name)

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        extracted_agent_name = agent_name_holder[0] if agent_name_holder else None
        if extracted_agent_name is not None:
            _destroy_agent(extracted_agent_name)
        raise ChangelingDeployError(
            f"Deployment verification of '{changeling_name}' timed out after "
            f"{process_timeout_seconds}s. The modal run process was killed."
        ) from None

    except Exception:
        # Ensure process is cleaned up on any unexpected error
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
