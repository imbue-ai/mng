#!/usr/bin/env python3
"""Benchmark script for `mngr create --message` path.

Run with:
    uv run python scripts/benchmark_create_message.py --trials 20
"""

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from dataclasses import field


@dataclass
class TrialResult:
    elapsed: float
    retries: int
    message_correct: bool
    message_truncated: bool
    extra_newlines: bool
    error: str | None = None


@dataclass
class BenchmarkResult:
    results: list[TrialResult] = field(default_factory=list)
    failures: int = 0

    @property
    def successful(self) -> list[TrialResult]:
        return [r for r in self.results if r.error is None]

    @property
    def avg_time(self) -> float:
        times = [r.elapsed for r in self.successful]
        return sum(times) / len(times) if times else 0

    @property
    def min_time(self) -> float:
        times = [r.elapsed for r in self.successful]
        return min(times) if times else 0

    @property
    def max_time(self) -> float:
        times = [r.elapsed for r in self.successful]
        return max(times) if times else 0

    @property
    def avg_retries(self) -> float:
        retries = [r.retries for r in self.successful]
        return sum(retries) / len(retries) if retries else 0

    @property
    def total_retries(self) -> int:
        return sum(r.retries for r in self.successful)

    @property
    def message_errors(self) -> int:
        return sum(1 for r in self.successful if not r.message_correct)

    @property
    def truncations(self) -> int:
        return sum(1 for r in self.successful if r.message_truncated)

    @property
    def newline_errors(self) -> int:
        return sum(1 for r in self.successful if r.extra_newlines)


def run_command(cmd: list[str], timeout: float = 120) -> tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "timeout"


def get_tmux_prefix() -> str:
    """Get the mngr tmux session prefix from config."""
    # Read from mngr list output to find the prefix
    success, stdout, _ = run_command(["tmux", "list-sessions", "-F", "#{session_name}"])
    if success:
        for line in stdout.strip().split("\n"):
            if "bench-create" in line:
                # Extract prefix (everything before the agent name)
                idx = line.find("bench-create")
                if idx > 0:
                    return line[:idx]
    return "mngr_"  # fallback


def capture_tmux_pane(session_name: str) -> str | None:
    """Capture the content of a tmux pane."""
    success, stdout, _ = run_command(
        ["tmux", "capture-pane", "-t", session_name, "-p", "-S", "-100"],
        timeout=5,
    )
    return stdout if success else None


def find_session_for_agent(agent_name: str) -> str | None:
    """Find the tmux session name for an agent."""
    success, stdout, _ = run_command(["tmux", "list-sessions", "-F", "#{session_name}"])
    if not success:
        return None
    for line in stdout.strip().split("\n"):
        if agent_name in line:
            return line
    return None


def verify_message_in_pane(pane_content: str, expected_message: str) -> tuple[bool, bool, bool]:
    """Verify the message appears correctly in the pane.

    Returns (message_correct, message_truncated, extra_newlines)
    """
    # The message should appear in Claude's conversation after the prompt symbol
    # Look for the message after a prompt indicator like ">" or the input area
    lines = pane_content.split("\n")

    message_found = False
    message_truncated = False
    extra_newlines = False

    for i, line in enumerate(lines):
        # Look for the exact message in the pane
        if expected_message in line:
            message_found = True
            # Check for extra newlines - if the message appears across multiple lines
            # when it shouldn't, that indicates Enter was interpreted as newline
            break
        # Check for truncated message (first part appears but not the full thing)
        if len(expected_message) > 5 and expected_message[:5] in line and expected_message not in line:
            message_truncated = True

    # Check for extra blank lines or newlines in the input area
    # This is a heuristic - look for the message split across lines
    for i, line in enumerate(lines):
        if expected_message[:10] in line if len(expected_message) >= 10 else expected_message in line:
            # Check if continuation of message is on next line (indicating unwanted newline)
            if i + 1 < len(lines) and len(expected_message) > 10:
                next_line = lines[i + 1].strip()
                # If part of message continues on next line, that's an extra newline
                if next_line and expected_message[10:20] in next_line:
                    extra_newlines = True
            break

    return message_found, message_truncated, extra_newlines


def destroy_agent(name: str) -> bool:
    """Destroy a test agent."""
    success, _, _ = run_command(["uv", "run", "mngr", "destroy", name, "--force"], timeout=30)
    return success


def create_with_message_and_verify(name: str, message: str) -> TrialResult:
    """Create agent with message and verify it was sent correctly."""
    start = time.time()
    success, stdout, stderr = run_command(
        [
            "uv",
            "run",
            "mngr",
            "create",
            name,
            "--agent-type",
            "claude",
            "--message",
            message,
            "--no-connect",
            "--no-ensure-clean",
            "--await-ready",
            "-v",
        ],
        timeout=120,
    )
    elapsed = time.time() - start

    if not success:
        # Show full error for debugging
        full_error = stderr if stderr else stdout
        print(f"\n\nFULL ERROR:\n{full_error}\n")
        return TrialResult(
            elapsed=elapsed,
            retries=0,
            message_correct=False,
            message_truncated=False,
            extra_newlines=False,
            error=f"Create failed: {full_error[:500]}",
        )

    combined = stdout + stderr
    if "Message submitted successfully" not in combined:
        return TrialResult(
            elapsed=elapsed,
            retries=0,
            message_correct=False,
            message_truncated=False,
            extra_newlines=False,
            error=f"Message not submitted: {combined[:200]}",
        )

    # Count retries
    retry_count = combined.count("cleaning up and retrying")

    # Find and capture the tmux session to verify message content
    session_name = find_session_for_agent(name)
    if session_name is None:
        return TrialResult(
            elapsed=elapsed,
            retries=retry_count,
            message_correct=False,
            message_truncated=False,
            extra_newlines=False,
            error="Could not find tmux session",
        )

    # Give Claude a moment to process and display the message
    time.sleep(0.5)

    pane_content = capture_tmux_pane(session_name)
    if pane_content is None:
        return TrialResult(
            elapsed=elapsed,
            retries=retry_count,
            message_correct=False,
            message_truncated=False,
            extra_newlines=False,
            error="Could not capture tmux pane",
        )

    message_correct, message_truncated, extra_newlines = verify_message_in_pane(pane_content, message)

    return TrialResult(
        elapsed=elapsed,
        retries=retry_count,
        message_correct=message_correct,
        message_truncated=message_truncated,
        extra_newlines=extra_newlines,
        error=None
        if message_correct
        else f"Message verification failed (truncated={message_truncated}, newlines={extra_newlines})",
    )


def run_benchmark(trials: int) -> BenchmarkResult:
    """Run the benchmark."""
    result = BenchmarkResult()

    for i in range(trials):
        agent_name = f"bench-create-{i}"
        # Use a message that's easy to verify and long enough to catch truncation
        message = f"benchmark test message number {i} with some extra text to verify"

        sys.stdout.write(f"\r  Trial {i + 1}/{trials}: creating with message...")
        sys.stdout.flush()

        try:
            trial_result = create_with_message_and_verify(agent_name, message)
            result.results.append(trial_result)

            if trial_result.error:
                result.failures += 1
                print(f"\r  Trial {i + 1}/{trials}: FAILED - {trial_result.error[:50]}     ")
            else:
                status = "OK" if trial_result.message_correct else "MSG_ERR"
                print(
                    f"\r  Trial {i + 1}/{trials}: {trial_result.elapsed:.2f}s, {trial_result.retries} retries, {status}     "
                )
        finally:
            destroy_agent(agent_name)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark mngr create --message")
    parser.add_argument("--trials", type=int, default=20, help="Number of trials")
    args = parser.parse_args()

    print(f"Running benchmark for 'mngr create --message' with {args.trials} trials")
    print()

    result = run_benchmark(args.trials)

    print()
    print("=" * 60)
    print("Results:")
    print(f"  Successful trials: {len(result.successful)}/{args.trials}")
    print(f"  Failures: {result.failures}")
    if result.successful:
        print(f"  Avg time: {result.avg_time:.2f}s")
        print(f"  Min time: {result.min_time:.2f}s")
        print(f"  Max time: {result.max_time:.2f}s")
        print(f"  Avg retries: {result.avg_retries:.2f}")
        print(f"  Total retries: {result.total_retries}")
        print()
        print("Message verification:")
        print(f"  Message errors: {result.message_errors}")
        print(f"  Truncations: {result.truncations}")
        print(f"  Extra newlines: {result.newline_errors}")
    print("=" * 60)


if __name__ == "__main__":
    main()
