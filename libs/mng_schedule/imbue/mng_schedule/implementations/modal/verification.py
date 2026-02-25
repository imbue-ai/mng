# Post-deploy verification for mng schedule.
#
# Verifies that a deployed schedule actually works by invoking it once
# via `modal run`, streaming output, detecting agent creation, and
# optionally destroying the verification agent.
#
# This module is excluded from unit test coverage because it requires
# real Modal and mng infrastructure to execute (similar to cron_runner.py).
# It is exercised by the acceptance test in test_schedule_add.py.
import pdb
import re
import subprocess
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.pure import pure
from imbue.mng_schedule.errors import ScheduleDeployError

VERIFICATION_TIMEOUT_SECONDS: Final[float] = 900.0


@pure
def build_modal_run_command(cron_runner_path: Path, modal_env_name: str) -> list[str]:
    """Build the modal run CLI command for invoking the deployed function once."""
    return ["uv", "run", "modal", "run", "--env", modal_env_name, str(cron_runner_path)]


# Regex to extract agent name from mng output.
# The mng create command logs a line like: "Starting agent <agent-name> ..."
_AGENT_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"Starting agent\s+(\S+)")


def _destroy_agent(agent_name: str) -> None:
    """Destroy an agent by name (no-op if it doesn't exist, since --force is used)."""
    logger.info("Destroying verification agent '{}'", agent_name)
    pdb.set_trace()
    with ConcurrencyGroup(name="mng-destroy") as cg:
        result = cg.run_process_to_completion(
            ["uv", "run", "mng", "destroy", "--force", agent_name],
            is_checked_after=False,
            timeout=300.0,
        )
    if result.returncode != 0:
        logger.warning("mng destroy failed (exit {}): {}", result.returncode, result.stderr)


def _stream_process_output(
    process: subprocess.Popen[str],
    error_event: threading.Event,
    error_lines: list[str],
    # Mutable list to capture extracted agent name (thread-safe single write).
    agent_name_holder: list[str],
    trigger_name: str,
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

        # Extract agent name from mng create output
        if not agent_name_holder:
            match = _AGENT_NAME_PATTERN.search(stripped)
            if match is not None:
                candidate = match.group(1)
                agent_name_holder.append(candidate)
                logger.debug("Extracted agent name from output: {}", candidate)


def verify_schedule_deployment(
    trigger_name: str,
    modal_env_name: str,
    is_finish_initial_run: bool,
    env: Mapping[str, str],
    cron_runner_path: Path,
    process_timeout_seconds: float = VERIFICATION_TIMEOUT_SECONDS,
) -> None:
    """Verify deployment by invoking the deployed function and waiting for it to exit.

    After modal deploy, this function:
    1. Runs `modal run` to invoke the deployed cron function once
    2. Streams output and monitors for errors
    3. Waits for the process to exit
    4. If is_finish_initial_run is False, destroys the agent after it starts
    5. If is_finish_initial_run is True, leaves the agent running
    6. Raises ScheduleDeployError on timeout, non-zero exit, or detected errors
    """
    cmd = build_modal_run_command(cron_runner_path, modal_env_name)
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
        args=(process, error_event, error_lines, agent_name_holder, trigger_name),
        daemon=True,
    )
    log_thread.start()

    try:
        exit_code = process.wait(timeout=process_timeout_seconds)

        # Wait for the log thread to finish processing remaining buffered output
        # so that agent_name_holder is fully populated before we read it.
        log_thread.join(timeout=5.0)

        extracted_agent_name = agent_name_holder[0] if agent_name_holder else None

        if error_event.is_set():
            if extracted_agent_name is not None:
                _destroy_agent(extracted_agent_name)
            error_detail = "\n".join(error_lines) if error_lines else "See output above"
            raise ScheduleDeployError(
                f"Error detected during deployment verification of schedule '{trigger_name}':\n{error_detail}"
            )

        if exit_code != 0:
            if extracted_agent_name is not None:
                _destroy_agent(extracted_agent_name)
            raise ScheduleDeployError(
                f"Deployment verification of schedule '{trigger_name}' failed "
                f"(modal run exited with code {exit_code}). See output above for details."
            )

        logger.info("modal run completed successfully for schedule '{}'", trigger_name)

        if not is_finish_initial_run:
            if extracted_agent_name is not None:
                _destroy_agent(extracted_agent_name)
            else:
                logger.warning(
                    "Could not extract agent name from output -- skipping cleanup. "
                    "The agent may still be running and will need manual cleanup."
                )

        logger.info("Deployment verification complete for schedule '{}'", trigger_name)

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        log_thread.join(timeout=5.0)
        extracted_agent_name = agent_name_holder[0] if agent_name_holder else None
        if extracted_agent_name is not None:
            _destroy_agent(extracted_agent_name)
        raise ScheduleDeployError(
            f"Deployment verification of schedule '{trigger_name}' timed out after "
            f"{process_timeout_seconds}s. The modal run process was killed."
        ) from None

    except Exception:
        # Ensure process is cleaned up on any unexpected error
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
