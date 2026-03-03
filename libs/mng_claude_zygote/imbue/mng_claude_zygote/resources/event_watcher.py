#!/usr/bin/env python3
"""Event watcher for changeling agents.

Streams events from ``mng events --follow --filter`` and delivers them
to the primary agent via ``mng message`` with debouncing and rate limiting.

The watcher delegates all event discovery, deduplication, and filtering
to the ``mng events`` command (run as a subprocess). This script handles:

- At-least-once delivery with minimal duplicates on restart
- Token-bucket rate limiting (burst + sustained rate)
- Delivery envelope formatting (time since last message, rate warnings)
- Subprocess lifecycle (restart on exit)

Usage: python3 event_watcher.py

Environment:
  MNG_AGENT_STATE_DIR  - agent state directory (contains events/)
  MNG_AGENT_WORK_DIR   - agent working directory (contains .changelings/)
  MNG_AGENT_NAME       - name of the primary agent to send messages to
  MNG_HOST_DIR         - host data directory (for log output)
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from typing import Final

from loguru import logger

try:
    from imbue.mng_claude_zygote.resources.watcher_common import load_watchers_section
    from imbue.mng_claude_zygote.resources.watcher_common import require_env
    from imbue.mng_claude_zygote.resources.watcher_common import setup_watcher_logging
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from watcher_common import load_watchers_section  # type: ignore[no-redef]
    from watcher_common import require_env  # type: ignore[no-redef]
    from watcher_common import setup_watcher_logging  # type: ignore[no-redef]


# -- Constants --

_DEFAULT_CEL_FILTER: Final[str] = (
    '!source.startsWith("logs/") || (source.startsWith("logs/") && (level == "ERROR" || level == "WARNING"))'
)

_DEFAULT_BURST_SIZE: Final[int] = 5
_DEFAULT_MAX_MESSAGES_PER_MINUTE: Final[int] = 10
_DEFAULT_HIGH_RATE_WARNING_THRESHOLD: Final[int] = 8

_DELIVERY_STATE_FILENAME: Final[str] = ".event_delivery_state.json"

_SUBPROCESS_RESTART_DELAY_SECONDS: Final[float] = 5.0

_MESSAGE_SEND_TIMEOUT_SECONDS: Final[float] = 120.0

# How often the delivery loop polls for buffered events
_DELIVERY_POLL_INTERVAL_SECONDS: Final[float] = 0.5


# -- Settings --


class _EventWatcherSettings:
    """Parsed event watcher settings from settings.toml."""

    def __init__(
        self,
        cel_filter: str = _DEFAULT_CEL_FILTER,
        burst_size: int = _DEFAULT_BURST_SIZE,
        max_messages_per_minute: int = _DEFAULT_MAX_MESSAGES_PER_MINUTE,
        high_rate_warning_threshold: int = _DEFAULT_HIGH_RATE_WARNING_THRESHOLD,
    ) -> None:
        self.cel_filter = cel_filter
        self.burst_size = burst_size
        self.max_messages_per_minute = max_messages_per_minute
        self.high_rate_warning_threshold = high_rate_warning_threshold


def _load_watcher_settings(agent_work_dir: Path) -> _EventWatcherSettings:
    """Load event watcher settings from settings.toml, falling back to defaults."""
    watchers = load_watchers_section(agent_work_dir)
    if not watchers:
        return _EventWatcherSettings()
    return _EventWatcherSettings(
        cel_filter=watchers.get("event_cel_filter", _DEFAULT_CEL_FILTER),
        burst_size=watchers.get("event_burst_size", _DEFAULT_BURST_SIZE),
        max_messages_per_minute=watchers.get("max_event_messages_per_minute", _DEFAULT_MAX_MESSAGES_PER_MINUTE),
        high_rate_warning_threshold=watchers.get(
            "high_rate_warning_threshold_per_minute", _DEFAULT_HIGH_RATE_WARNING_THRESHOLD
        ),
    )


# -- Delivery state --


class _DeliveryState:
    """Tracks which events have been delivered for at-least-once semantics."""

    def __init__(
        self,
        last_event_id: str = "",
        last_timestamp: str = "",
        last_delivery_monotonic: float = 0.0,
    ) -> None:
        self.last_event_id = last_event_id
        self.last_timestamp = last_timestamp
        self.last_delivery_monotonic = last_delivery_monotonic


def _load_delivery_state(state_file: Path) -> _DeliveryState:
    """Load delivery state from file, returning defaults if not found or corrupt."""
    try:
        if not state_file.is_file():
            return _DeliveryState()
        raw = json.loads(state_file.read_text())
        return _DeliveryState(
            last_event_id=raw.get("last_event_id", ""),
            last_timestamp=raw.get("last_timestamp", ""),
        )
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("Failed to load delivery state from {}: {}", state_file, exc)
        return _DeliveryState()


def _save_delivery_state(state_file: Path, state: _DeliveryState) -> None:
    """Persist delivery state to file atomically (write tmp + rename)."""
    data = {"last_event_id": state.last_event_id, "last_timestamp": state.last_timestamp}
    tmp_file = state_file.with_suffix(".tmp")
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file.write_text(json.dumps(data))
        tmp_file.rename(state_file)
    except OSError as exc:
        logger.error("Failed to save delivery state to {}: {}", state_file, exc)


# -- Rate limiting --


class _TokenBucket:
    """Token bucket rate limiter.

    Starts with burst_size tokens. Tokens refill at rate_per_second.
    """

    def __init__(self, burst_size: int, rate_per_second: float) -> None:
        self._burst_size = burst_size
        self._rate_per_second = rate_per_second
        self._tokens = float(burst_size)
        self._last_refill_time = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if a token was available."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    def time_until_token(self) -> float:
        """Seconds until next token is available. Returns 0.0 if one is available now."""
        self._refill()
        if self._tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self._tokens
        if self._rate_per_second <= 0:
            return float("inf")
        return deficit / self._rate_per_second

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill_time
        self._last_refill_time = now
        self._tokens = min(float(self._burst_size), self._tokens + elapsed * self._rate_per_second)


class _SendRateTracker:
    """Tracks message send rate over a sliding 60-second window."""

    def __init__(self) -> None:
        self._send_times: list[float] = []

    def record_send(self) -> None:
        self._send_times.append(time.monotonic())
        self._prune()

    def messages_per_minute(self) -> float:
        """Return the number of messages sent in the last 60 seconds."""
        self._prune()
        return float(len(self._send_times))

    def _prune(self) -> None:
        cutoff = time.monotonic() - 60.0
        self._send_times = [t for t in self._send_times if t > cutoff]


# -- Catch-up filtering --


def _should_skip_for_catchup(line_json: dict[str, Any], delivery_state: _DeliveryState) -> bool:
    """Return True if this event was already delivered in a prior run and should be skipped.

    Compares by event_id (exact match) and timestamp (skip if <= last delivered).
    """
    if not delivery_state.last_event_id and not delivery_state.last_timestamp:
        return False

    event_id = line_json.get("event_id", "")
    if event_id and event_id == delivery_state.last_event_id:
        return True

    timestamp = line_json.get("timestamp", "")
    if timestamp and delivery_state.last_timestamp and timestamp <= delivery_state.last_timestamp:
        return True

    return False


# -- Message formatting --


def _format_time_since_last(seconds: float) -> str:
    """Format a duration as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def _format_delivery_message(
    event_lines: list[str],
    time_since_last_message_seconds: float | None,
    rate_warning: str | None,
) -> str:
    """Format a delivery envelope with event lines and metadata."""
    parts: list[str] = []

    # Header
    count = len(event_lines)
    parts.append(f"[Event watcher] {count} new event(s)")

    if time_since_last_message_seconds is not None:
        parts.append(f"  Time since last message: {_format_time_since_last(time_since_last_message_seconds)}")

    if rate_warning:
        parts.append(f"  WARNING: {rate_warning}")

    parts.append("")

    for line in event_lines:
        parts.append(line)

    return "\n".join(parts)


# -- Message sending --


def _send_message(agent_name: str, message: str) -> bool:
    """Send a message to the agent via mng message. Returns True on success."""
    try:
        result = subprocess.run(
            ["uv", "run", "mng", "message", agent_name, "-m", message],
            capture_output=True,
            text=True,
            timeout=_MESSAGE_SEND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.error("Timed out sending message to {}", agent_name)
        return False
    except OSError as exc:
        logger.error("Failed to invoke mng message subprocess: {}", exc)
        return False

    if result.returncode != 0:
        logger.error("mng message returned non-zero for {}: {}", agent_name, result.stderr)
        return False

    return True


# -- Subprocess management --


def _start_events_subprocess(agent_name: str, cel_filter: str) -> subprocess.Popen[str]:
    """Start ``mng events <agent_name> --follow --filter <cel_filter>`` as a subprocess."""
    cmd = ["uv", "run", "mng", "events", agent_name, "--follow"]
    if cel_filter:
        cmd.extend(["--filter", cel_filter])
    logger.info("Starting events subprocess: {}", " ".join(cmd))
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _read_events_from_subprocess(
    proc: subprocess.Popen[str],
    event_buffer: list[str],
    buffer_lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    """Read JSONL lines from subprocess stdout into the event buffer (thread target)."""
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if stop_event.is_set():
                break
            stripped = line.strip()
            if not stripped:
                continue
            with buffer_lock:
                event_buffer.append(stripped)
    except Exception as exc:
        if not stop_event.is_set():
            logger.error("Error reading from events subprocess: {}", exc)


def _drain_stderr(
    proc: subprocess.Popen[str],
    stop_event: threading.Event,
) -> None:
    """Read and log stderr from the subprocess (daemon thread target)."""
    assert proc.stderr is not None
    try:
        for line in proc.stderr:
            if stop_event.is_set():
                break
            stripped = line.strip()
            if stripped:
                logger.warning("mng events stderr: {}", stripped)
    except Exception:
        pass


# -- Delivery loop --


def _run_delivery_loop(
    settings: _EventWatcherSettings,
    agent_name: str,
    state_file: Path,
    event_buffer: list[str],
    buffer_lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    """Main delivery loop: drain buffer, rate-limit, format, and deliver to agent."""
    delivery_state = _load_delivery_state(state_file)
    is_catching_up = bool(delivery_state.last_event_id or delivery_state.last_timestamp)

    if is_catching_up:
        logger.info(
            "Resuming from last delivered event: {} ({})",
            delivery_state.last_event_id,
            delivery_state.last_timestamp,
        )

    token_bucket = _TokenBucket(
        burst_size=settings.burst_size,
        rate_per_second=settings.max_messages_per_minute / 60.0,
    )
    rate_tracker = _SendRateTracker()

    while not stop_event.is_set():
        # Wait for a token to become available
        wait_time = token_bucket.time_until_token()
        if wait_time > 0:
            stop_event.wait(timeout=min(wait_time, 1.0))
            if stop_event.is_set():
                break
            continue

        # Drain the buffer
        with buffer_lock:
            pending = list(event_buffer)
            event_buffer.clear()

        if not pending:
            stop_event.wait(timeout=_DELIVERY_POLL_INTERVAL_SECONDS)
            continue

        # Parse and filter for catch-up
        deliverable_lines: list[str] = []
        last_parsed: dict[str, Any] = {}
        for line in pending:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSONL line: {}", line[:200])
                continue

            if is_catching_up and _should_skip_for_catchup(parsed, delivery_state):
                continue

            # Once we see a non-skipped event, catch-up is done
            is_catching_up = False
            deliverable_lines.append(line)
            last_parsed = parsed

        if not deliverable_lines:
            continue

        # Consume a rate-limit token
        if not token_bucket.consume():
            # No token available (shouldn't happen since we waited above, but be safe)
            with buffer_lock:
                event_buffer[0:0] = deliverable_lines
            continue

        # Compute time since last message
        time_since_last: float | None = None
        if delivery_state.last_delivery_monotonic > 0:
            time_since_last = time.monotonic() - delivery_state.last_delivery_monotonic

        # Check if rate warning is needed
        rate_warning: str | None = None
        current_rate = rate_tracker.messages_per_minute()
        if current_rate >= settings.high_rate_warning_threshold:
            rate_warning = (
                f"High event rate: {current_rate:.0f} messages/min "
                f"(threshold: {settings.high_rate_warning_threshold}/min)"
            )

        # Format and send
        message = _format_delivery_message(deliverable_lines, time_since_last, rate_warning)
        logger.info("Sending {} event(s) to '{}'", len(deliverable_lines), agent_name)

        if _send_message(agent_name, message):
            rate_tracker.record_send()
            delivery_state.last_event_id = last_parsed.get("event_id", "")
            delivery_state.last_timestamp = last_parsed.get("timestamp", "")
            delivery_state.last_delivery_monotonic = time.monotonic()
            _save_delivery_state(state_file, delivery_state)
            logger.info("Delivered {} event(s), state updated", len(deliverable_lines))
        else:
            # Put events back for retry
            logger.warning("Failed to deliver {} event(s), will retry", len(deliverable_lines))
            with buffer_lock:
                event_buffer[0:0] = deliverable_lines


# -- Main --


def main() -> None:
    agent_state_dir = Path(require_env("MNG_AGENT_STATE_DIR"))
    agent_work_dir = Path(require_env("MNG_AGENT_WORK_DIR"))
    agent_name = require_env("MNG_AGENT_NAME")
    host_dir = Path(require_env("MNG_HOST_DIR"))

    setup_watcher_logging("event_watcher", host_dir / "events" / "logs")

    settings = _load_watcher_settings(agent_work_dir)

    # Delivery state persistence
    state_dir = agent_state_dir / "events"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / _DELIVERY_STATE_FILENAME

    logger.info("Event watcher started")
    logger.info("  Agent name: {}", agent_name)
    logger.info("  CEL filter: {}", settings.cel_filter)
    logger.info("  Burst size: {}", settings.burst_size)
    logger.info("  Max messages/min: {}", settings.max_messages_per_minute)
    logger.info("  Rate warning threshold: {}/min", settings.high_rate_warning_threshold)
    logger.info("  State file: {}", state_file)

    stop_event = threading.Event()
    event_buffer: list[str] = []
    buffer_lock = threading.Lock()

    # Start the long-lived delivery thread
    delivery_thread = threading.Thread(
        target=_run_delivery_loop,
        args=(settings, agent_name, state_file, event_buffer, buffer_lock, stop_event),
        daemon=True,
    )
    delivery_thread.start()

    try:
        while not stop_event.is_set():
            proc = _start_events_subprocess(agent_name, settings.cel_filter)

            # Reader thread feeds subprocess stdout into the shared buffer
            reader_thread = threading.Thread(
                target=_read_events_from_subprocess,
                args=(proc, event_buffer, buffer_lock, stop_event),
                daemon=True,
            )
            reader_thread.start()

            # Stderr drain thread
            stderr_thread = threading.Thread(
                target=_drain_stderr,
                args=(proc, stop_event),
                daemon=True,
            )
            stderr_thread.start()

            # Wait for subprocess to exit
            proc.wait()
            logger.warning("mng events subprocess exited with code {}", proc.returncode)

            if stop_event.is_set():
                break

            logger.info("Restarting events subprocess in {}s", _SUBPROCESS_RESTART_DELAY_SECONDS)
            stop_event.wait(timeout=_SUBPROCESS_RESTART_DELAY_SECONDS)

    except KeyboardInterrupt:
        logger.info("Event watcher stopping (KeyboardInterrupt)")
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
