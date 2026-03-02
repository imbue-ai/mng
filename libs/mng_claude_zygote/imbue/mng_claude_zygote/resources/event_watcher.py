#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["watchdog"]
# ///
"""Event watcher for changeling agents.

Watches event log files (logs/<source>/events.jsonl) for new entries and
sends unhandled events to the primary agent via ``uv run mng message``.

Uses the watchdog library for fast filesystem event detection, with
periodic mtime-based polling as a safety net to catch any events that
watchdog may have dropped.

Watched sources (default):
  logs/messages/events.jsonl     - conversation messages
  logs/scheduled/events.jsonl    - scheduled trigger events
  logs/mng_agents/events.jsonl   - agent state transitions
  logs/stop/events.jsonl         - agent stop events

Each event in these files includes the standard envelope (timestamp, type,
event_id, source) so the watcher can format meaningful messages.

Usage: uv run event_watcher.py

Environment:
  MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)
  MNG_AGENT_NAME       - name of the primary agent to send messages to
  MNG_HOST_DIR         - host data directory (contains logs/ for log output)
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class _Logger:
    """Simple dual-output logger: writes to both stdout and a log file."""

    def __init__(self, log_file: Path) -> None:
        self._log_file = log_file
        self._log_file.parent.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        now = time.time()
        fractional_ns = int((now % 1) * 1_000_000_000)
        utc_struct = time.gmtime(now)
        return time.strftime("%Y-%m-%dT%H:%M:%S", utc_struct) + f".{fractional_ns:09d}Z"

    def info(self, msg: str) -> None:
        line = f"[{self._timestamp()}] {msg}"
        print(line, flush=True)
        try:
            with self._log_file.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def debug(self, msg: str) -> None:
        line = f"[{self._timestamp()}] [debug] {msg}"
        try:
            with self._log_file.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass


def _load_watcher_settings(agent_state_dir: Path) -> dict[str, object]:
    """Load watcher settings from settings.toml, falling back to defaults."""
    defaults: dict[str, object] = {
        "poll_interval": 3,
        "sources": ["messages", "scheduled", "mng_agents", "stop"],
    }
    settings_path = agent_state_dir / "settings.toml"
    try:
        if not settings_path.exists():
            return defaults
        raw = tomllib.loads(settings_path.read_text())
        watchers = raw.get("watchers", {})
        return {
            "poll_interval": watchers.get("event_poll_interval_seconds", defaults["poll_interval"]),
            "sources": watchers.get("watched_event_sources", defaults["sources"]),
        }
    except Exception as exc:
        print(f"WARNING: failed to load settings: {exc}", file=sys.stderr)
        return defaults


class _ChangeHandler(FileSystemEventHandler):
    """Watchdog handler that signals the main loop on any filesystem change."""

    def __init__(self, wake_event: threading.Event) -> None:
        super().__init__()
        self._wake_event = wake_event

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._wake_event.set()


def _get_offset(offsets_dir: Path, source: str) -> int:
    """Read the current line offset for a source."""
    offset_file = offsets_dir / f"{source}.offset"
    try:
        return int(offset_file.read_text().strip())
    except (OSError, ValueError):
        return 0


def _set_offset(offsets_dir: Path, source: str, offset: int) -> None:
    """Write the current line offset for a source."""
    offset_file = offsets_dir / f"{source}.offset"
    offset_file.write_text(str(offset))


def _check_and_send_new_events(
    events_file: Path,
    source: str,
    offsets_dir: Path,
    agent_name: str,
    log: _Logger,
) -> None:
    """Check for new lines in an events.jsonl file and send them via mng message."""
    if not events_file.is_file():
        return

    current_offset = _get_offset(offsets_dir, source)

    try:
        with events_file.open() as f:
            all_lines = f.readlines()
    except OSError as exc:
        log.info(f"ERROR: failed to read {events_file}: {exc}")
        return

    total_lines = len(all_lines)
    if total_lines <= current_offset:
        return

    new_lines = all_lines[current_offset:total_lines]
    new_text = "".join(new_lines).strip()
    if not new_text:
        return

    new_count = total_lines - current_offset
    log.info(f"Found {new_count} new event(s) from source '{source}' (offset {current_offset} -> {total_lines})")
    log.debug(f"New events from {source}: {new_text[:500]}")

    message = f"New {source} event(s):\n{new_text}"

    log.info(f"Sending {new_count} event(s) from '{source}' to agent '{agent_name}'")
    try:
        result = subprocess.run(
            ["uv", "run", "mng", "message", agent_name, "-m", message],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            _set_offset(offsets_dir, source, total_lines)
            log.info(f"Events sent successfully, offset updated to {total_lines}")
        else:
            log.info(f"ERROR: failed to send events from {source} to {agent_name}: {result.stderr}")
    except subprocess.TimeoutExpired:
        log.info(f"ERROR: timed out sending events from {source} to {agent_name}")
    except OSError as exc:
        log.info(f"ERROR: failed to run mng message: {exc}")


def _check_all_sources(
    logs_dir: Path,
    watched_sources: list[str],
    offsets_dir: Path,
    agent_name: str,
    log: _Logger,
) -> None:
    """Check all watched sources for new events."""
    for source in watched_sources:
        events_file = logs_dir / source / "events.jsonl"
        _check_and_send_new_events(events_file, source, offsets_dir, agent_name, log)


def _mtime_poll(
    logs_dir: Path,
    watched_sources: list[str],
    mtime_cache: dict[str, tuple[float, int]],
    log: _Logger,
) -> bool:
    """Scan all watched event files for mtime/size changes.

    Returns True if any file was created, removed, or modified since the
    last scan. This catches changes that watchdog may have missed.
    """
    is_changed = False
    current_keys: set[str] = set()

    for source in watched_sources:
        source_dir = logs_dir / source
        if not source_dir.exists():
            continue
        try:
            for entry in source_dir.iterdir():
                key = str(entry)
                current_keys.add(key)
                try:
                    stat = entry.stat()
                    current = (stat.st_mtime, stat.st_size)
                except OSError:
                    continue

                previous = mtime_cache.get(key)
                if previous != current:
                    mtime_cache[key] = current
                    is_changed = True
                    if previous is None:
                        log.debug(f"New file detected: {entry}")
                    else:
                        log.debug(f"File changed: {entry}")
        except OSError:
            continue

    # Detect removed files
    removed_keys = set(mtime_cache.keys()) - current_keys
    for key in removed_keys:
        del mtime_cache[key]
        is_changed = True
        log.debug(f"File removed: {key}")

    return is_changed


def main() -> None:
    agent_state_dir_str = os.environ.get("MNG_AGENT_STATE_DIR", "")
    if not agent_state_dir_str:
        print("ERROR: MNG_AGENT_STATE_DIR must be set", file=sys.stderr)
        sys.exit(1)
    agent_state_dir = Path(agent_state_dir_str)

    agent_name = os.environ.get("MNG_AGENT_NAME", "")
    if not agent_name:
        print("ERROR: MNG_AGENT_NAME must be set", file=sys.stderr)
        sys.exit(1)

    host_dir_str = os.environ.get("MNG_HOST_DIR", "")
    if not host_dir_str:
        print("ERROR: MNG_HOST_DIR must be set", file=sys.stderr)
        sys.exit(1)
    host_dir = Path(host_dir_str)

    logs_dir = agent_state_dir / "logs"
    offsets_dir = logs_dir / ".event_offsets"
    offsets_dir.mkdir(parents=True, exist_ok=True)

    log = _Logger(host_dir / "logs" / "event_watcher.log")

    settings = _load_watcher_settings(agent_state_dir)
    poll_interval = int(settings["poll_interval"])  # type: ignore[arg-type]
    watched_sources: list[str] = list(settings["sources"])  # type: ignore[arg-type]

    log.info("Event watcher started")
    log.info(f"  Agent data dir: {agent_state_dir}")
    log.info(f"  Agent name: {agent_name}")
    log.info(f"  Watched sources: {' '.join(watched_sources)}")
    log.info(f"  Offsets dir: {offsets_dir}")
    log.info(f"  Log file: {log._log_file}")
    log.info(f"  Poll interval: {poll_interval}s")
    log.info("  Using watchdog for file watching with periodic mtime polling")

    # Ensure watched directories exist (watchdog needs them to exist)
    watch_dirs: list[Path] = []
    for source in watched_sources:
        source_dir = logs_dir / source
        source_dir.mkdir(parents=True, exist_ok=True)
        watch_dirs.append(source_dir)

    # Set up watchdog observer
    wake_event = threading.Event()
    handler = _ChangeHandler(wake_event)
    observer = Observer()

    is_watchdog_active = False
    try:
        for source_dir in watch_dirs:
            observer.schedule(handler, str(source_dir), recursive=False)
        observer.start()
        is_watchdog_active = True
    except Exception as exc:
        log.info(f"WARNING: watchdog observer failed to start, falling back to polling only: {exc}")

    # Initialize the mtime cache with the current state
    mtime_cache: dict[str, tuple[float, int]] = {}
    _mtime_poll(logs_dir, watched_sources, mtime_cache, log)

    try:
        while True:
            # Wait for either a watchdog event or the poll interval timeout
            is_triggered_by_watchdog = wake_event.wait(timeout=poll_interval)
            wake_event.clear()

            if is_triggered_by_watchdog:
                log.debug("Woken by watchdog filesystem event")
            else:
                # Periodic poll: check mtimes for changes watchdog may have missed
                is_mtime_changed = _mtime_poll(logs_dir, watched_sources, mtime_cache, log)
                if is_mtime_changed:
                    log.info("Periodic mtime poll detected changes")

            # Always check all sources for new events
            _check_all_sources(logs_dir, watched_sources, offsets_dir, agent_name, log)
    except KeyboardInterrupt:
        log.info("Event watcher stopping (KeyboardInterrupt)")
    finally:
        if is_watchdog_active:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()
