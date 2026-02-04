#!/usr/bin/env python3
"""Benchmark script to compare message sending with/without pre-Enter sleep.

Run with:
    uv run python scripts/benchmark_enter_sleep.py --trials 100
"""

import argparse
import json
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


def run_command(cmd: list[str], timeout: float = 60) -> tuple[bool, str, str]:
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


def get_agent_state_dir(name: str) -> Path | None:
    """Get the agent's state directory path."""
    agents_dir = Path.home() / ".mngr" / "agents"
    if not agents_dir.exists():
        return None

    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        data_file = agent_dir / "data.json"
        if data_file.exists():
            with open(data_file) as f:
                data = json.load(f)
            if data.get("name") == name:
                return agent_dir
    return None


def wait_for_agent_ready(name: str, timeout: float = 60) -> bool:
    """Wait for agent to be in WAITING state by checking the waiting file."""
    start = time.time()
    while time.time() - start < timeout:
        state_dir = get_agent_state_dir(name)
        if state_dir:
            waiting_file = state_dir / "waiting"
            if waiting_file.exists():
                return True
        time.sleep(0.5)
    return False


def create_agent(name: str) -> bool:
    """Create a test agent without connecting or sending a message."""
    success, stdout, stderr = run_command(
        ["uv", "run", "mngr", "create", name, "--agent-type", "claude", "--no-connect", "--no-ensure-clean", "-v"],
        timeout=120,
    )
    if not success:
        print(f"\nFailed to create agent {name}: {stderr[:200]}")
    return success


def destroy_agent(name: str) -> bool:
    """Destroy a test agent."""
    success, _, _ = run_command(["uv", "run", "mngr", "destroy", name, "--force"], timeout=30)
    return success


def send_message_and_time(name: str, message: str) -> tuple[float, int] | None:
    """Send a message and return (elapsed_time, retry_count) or None on failure."""
    start = time.time()
    success, stdout, stderr = run_command(
        ["uv", "run", "mngr", "message", name, message, "-v"],
        timeout=60,
    )
    elapsed = time.time() - start

    if not success:
        print(f"\nMessage failed: {stderr[:200]}")
        return None

    # Count retries from log output
    combined = stdout + stderr
    retry_count = combined.count("cleaning up and retrying")

    return elapsed, retry_count


def run_benchmark(trials: int) -> BenchmarkResult:
    """Run the benchmark."""
    times: list[float] = []
    retry_counts: list[int] = []
    failures = 0

    for i in range(trials):
        agent_name = f"bench-{i}"

        # Sync venv at start of each trial to handle environment corruption
        sync_venv()

        sys.stdout.write(f"\r  Trial {i + 1}/{trials}: creating agent...")
        sys.stdout.flush()

        if not create_agent(agent_name):
            failures += 1
            continue

        try:
            sys.stdout.write(f"\r  Trial {i + 1}/{trials}: waiting for ready...")
            sys.stdout.flush()

            if not wait_for_agent_ready(agent_name, timeout=60):
                print(f"\r  Trial {i + 1}/{trials}: agent not ready after 60s, skipping")
                failures += 1
                continue

            sys.stdout.write(f"\r  Trial {i + 1}/{trials}: sending message...  ")
            sys.stdout.flush()

            result = send_message_and_time(agent_name, "test message for benchmark")
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
    parser = argparse.ArgumentParser(description="Benchmark Enter sleep timing")
    parser.add_argument("--trials", type=int, default=10, help="Number of trials")
    args = parser.parse_args()

    print(f"Running benchmark with {args.trials} trials")
    print("Check _BACKSPACE_SETTLE_SECONDS in base_agent.py for current sleep value")
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
