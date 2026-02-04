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
from pathlib import Path


@dataclass
class BenchmarkResult:
    times: list[float]
    retry_counts: list[int]
    failures: int

    @property
    def avg_time(self) -> float:
        return sum(self.times) / len(self.times) if self.times else 0

    @property
    def min_time(self) -> float:
        return min(self.times) if self.times else 0

    @property
    def max_time(self) -> float:
        return max(self.times) if self.times else 0

    @property
    def avg_retries(self) -> float:
        return sum(self.retry_counts) / len(self.retry_counts) if self.retry_counts else 0


def run_command(cmd: list[str], timeout: float = 120) -> tuple[bool, str, str]:
    """Run a command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "timeout"


def sync_venv() -> None:
    """Sync venv to ensure packages point to current worktree."""
    subprocess.run(
        ["uv", "sync", "--all-packages"],
        capture_output=True,
        timeout=60,
        cwd=Path(__file__).parent.parent,
    )


def destroy_agent(name: str) -> bool:
    """Destroy a test agent."""
    success, _, _ = run_command(["uv", "run", "mngr", "destroy", name, "--force"], timeout=30)
    return success


def create_with_message_and_time(name: str, message: str) -> tuple[float, int] | None:
    """Create agent with message and return (elapsed_time, retry_count) or None on failure."""
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
            "-v",
        ],
        timeout=120,
    )
    elapsed = time.time() - start

    if not success:
        print(f"\nCreate with message failed: {stderr[:500]}")
        return None

    # Check for successful submission
    combined = stdout + stderr
    if "Message submitted successfully" not in combined:
        print(f"\nMessage not submitted: {combined[:500]}")
        return None

    # Count retries from log output
    retry_count = combined.count("cleaning up and retrying")

    return elapsed, retry_count


def run_benchmark(trials: int) -> BenchmarkResult:
    """Run the benchmark."""
    times: list[float] = []
    retry_counts: list[int] = []
    failures = 0

    for i in range(trials):
        agent_name = f"bench-create-{i}"

        # Sync venv at start of each trial
        sync_venv()

        sys.stdout.write(f"\r  Trial {i + 1}/{trials}: creating with message...")
        sys.stdout.flush()

        try:
            result = create_with_message_and_time(agent_name, f"test message {i}")
            if result is None:
                failures += 1
            else:
                elapsed, retries = result
                times.append(elapsed)
                retry_counts.append(retries)
                print(f"\r  Trial {i + 1}/{trials}: {elapsed:.2f}s, {retries} retries     ")
        finally:
            destroy_agent(agent_name)

    return BenchmarkResult(times=times, retry_counts=retry_counts, failures=failures)


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
    print(f"  Successful trials: {len(result.times)}/{args.trials}")
    print(f"  Failures: {result.failures}")
    if result.times:
        print(f"  Avg time: {result.avg_time:.2f}s")
        print(f"  Min time: {result.min_time:.2f}s")
        print(f"  Max time: {result.max_time:.2f}s")
        print(f"  Avg retries: {result.avg_retries:.2f}")
        print(f"  Total retries: {sum(result.retry_counts)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
