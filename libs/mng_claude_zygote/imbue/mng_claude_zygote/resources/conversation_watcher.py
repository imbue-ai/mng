#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["watchdog"]
# ///
"""Conversation watcher for changeling agents.

Syncs messages from the llm database to the standard event log at
logs/messages/events.jsonl. Works as an ID-based syncer: reads event IDs
already present in the output file, queries recent responses from the DB
for all tracked conversations in a single batch, and appends any events
whose IDs are not yet in the file (in time order).

Each message event includes the full envelope (timestamp, type, event_id,
source) plus conversation_id and role, making every line self-describing.

Uses watchdog for fast filesystem event detection on the llm database
and conversations events file, with periodic mtime-based polling as
a safety net.

Usage: uv run conversation_watcher.py

Environment:
  MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)
  MNG_HOST_DIR         - host data directory (contains logs/ for log output)
"""

from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import sys
import threading
import time
import tomllib
from pathlib import Path

from watchdog.events import FileSystemEvent
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


@dataclasses.dataclass(frozen=True)
class _WatcherSettings:
    """Parsed conversation watcher settings from settings.toml."""

    poll_interval: int = 5


class _Logger:
    """Simple dual-output logger: writes to both stdout and a log file."""

    def __init__(self, log_file: Path) -> None:
        self.log_file_path = log_file
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        now = time.time()
        fractional_ns = int((now % 1) * 1_000_000_000)
        utc_struct = time.gmtime(now)
        return time.strftime("%Y-%m-%dT%H:%M:%S", utc_struct) + f".{fractional_ns:09d}Z"

    def info(self, msg: str) -> None:
        line = f"[{self._timestamp()}] {msg}"
        print(line, flush=True)
        try:
            with self.log_file_path.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def debug(self, msg: str) -> None:
        line = f"[{self._timestamp()}] [debug] {msg}"
        try:
            with self.log_file_path.open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass


def _load_watcher_settings(agent_state_dir: Path) -> _WatcherSettings:
    """Load conversation watcher settings from settings.toml."""
    settings_path = agent_state_dir / "settings.toml"
    try:
        if not settings_path.exists():
            return _WatcherSettings()
        raw = tomllib.loads(settings_path.read_text())
        watchers = raw.get("watchers", {})
        return _WatcherSettings(
            poll_interval=watchers.get("conversation_poll_interval_seconds", 5),
        )
    except Exception as exc:
        print(f"WARNING: failed to load settings: {exc}", file=sys.stderr)
        return _WatcherSettings()


def _get_llm_db_path() -> Path:
    """Locate the llm database file."""
    llm_user_path = os.environ.get("LLM_USER_PATH", "")
    if not llm_user_path:
        llm_user_path = str(Path.home() / ".config" / "io.datasette.llm")
    return Path(llm_user_path) / "logs.db"


def _get_tracked_conversation_ids(conversations_file: Path) -> set[str]:
    """Read tracked conversation IDs from logs/conversations/events.jsonl."""
    tracked_cids: set[str] = set()
    if not conversations_file.is_file():
        return tracked_cids
    try:
        with conversations_file.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tracked_cids.add(json.loads(line)["conversation_id"])
                except (json.JSONDecodeError, KeyError) as exc:
                    print(f"WARNING: malformed conversation event line: {exc}", file=sys.stderr)
                    continue
    except OSError as exc:
        print(f"WARNING: failed to read conversations file: {exc}", file=sys.stderr)
    return tracked_cids


def _get_existing_event_ids(messages_file: Path) -> set[str]:
    """Read event IDs already present in logs/messages/events.jsonl."""
    file_event_ids: set[str] = set()
    if not messages_file.is_file():
        return file_event_ids
    try:
        with messages_file.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    file_event_ids.add(json.loads(line)["event_id"])
                except (json.JSONDecodeError, KeyError) as exc:
                    print(f"WARNING: malformed message event line: {exc}", file=sys.stderr)
                    continue
    except OSError as exc:
        print(f"WARNING: failed to read messages file: {exc}", file=sys.stderr)
    return file_event_ids


def _sync_messages(
    db_path: Path,
    conversations_file: Path,
    messages_file: Path,
    log: _Logger,
) -> int:
    """Sync missing messages from the llm DB to logs/messages/events.jsonl.

    Uses an adaptive window: starts by fetching the most recent 200 responses
    from the DB and checks which event IDs are missing from the output file.
    If ALL fetched events are missing (suggesting the file is far behind),
    doubles the window and retries until it finds events already in the file
    or runs out of DB rows.

    Returns the number of new events synced.
    """
    if not db_path.is_file():
        log.debug(f"LLM database not found at {db_path}")
        return 0

    tracked_cids = _get_tracked_conversation_ids(conversations_file)
    if not tracked_cids:
        return 0

    file_event_ids = _get_existing_event_ids(messages_file)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"WARNING: cannot open database: {exc}", file=sys.stderr)
        return 0

    placeholders = ",".join("?" for _ in tracked_cids)
    cid_list = list(tracked_cids)

    # Adaptive window: start with 200 responses, double if all events are
    # missing (meaning we may need to look further back in the DB).
    window = 200
    missing_events: list[tuple[str, int, str]] = []

    while True:
        try:
            rows = conn.execute(
                f"SELECT id, datetime_utc, conversation_id, prompt, response "
                f"FROM responses "
                f"WHERE conversation_id IN ({placeholders}) "
                f"ORDER BY datetime_utc DESC "
                f"LIMIT ?",
                [*cid_list, window],
            ).fetchall()
        except sqlite3.Error as exc:
            print(f"WARNING: sqlite3 query error: {exc}", file=sys.stderr)
            break

        if not rows:
            break

        missing_events = []
        is_found_existing = False

        for row_id, ts, cid, prompt, response in rows:
            if prompt:
                eid = f"{row_id}-user"
                if eid in file_event_ids:
                    is_found_existing = True
                else:
                    missing_events.append(
                        (
                            ts,
                            0,
                            json.dumps(
                                {
                                    "timestamp": ts,
                                    "type": "message",
                                    "event_id": eid,
                                    "source": "messages",
                                    "conversation_id": cid,
                                    "role": "user",
                                    "content": prompt,
                                },
                                separators=(",", ":"),
                            ),
                        )
                    )

            if response:
                eid = f"{row_id}-assistant"
                if eid in file_event_ids:
                    is_found_existing = True
                else:
                    missing_events.append(
                        (
                            ts,
                            1,
                            json.dumps(
                                {
                                    "timestamp": ts,
                                    "type": "message",
                                    "event_id": eid,
                                    "source": "messages",
                                    "conversation_id": cid,
                                    "role": "assistant",
                                    "content": response,
                                },
                                separators=(",", ":"),
                            ),
                        )
                    )

        # If we found at least one event already in the file, we have looked
        # far enough back. If ALL events were missing and we got a full window
        # of rows, there may be even older missing events -- double and retry.
        if is_found_existing or len(rows) < window:
            break

        window *= 2

    conn.close()

    if not missing_events:
        return 0

    # Sort by (timestamp, sort_order) and append to file
    missing_events.sort(key=lambda x: (x[0], x[1]))

    messages_file.parent.mkdir(parents=True, exist_ok=True)
    with messages_file.open("a") as f:
        for _, _, event_json in missing_events:
            f.write(event_json + "\n")

    return len(missing_events)


def _mtime_poll(
    watch_paths: list[Path],
    mtime_cache: dict[str, tuple[float, int]],
    log: _Logger,
) -> bool:
    """Check watched files for mtime/size changes. Returns True if any changed."""
    is_changed = False
    current_keys: set[str] = set()

    for file_path in watch_paths:
        key = str(file_path)
        current_keys.add(key)
        try:
            stat = file_path.stat()
            current = (stat.st_mtime, stat.st_size)
        except OSError:
            if key in mtime_cache:
                del mtime_cache[key]
                is_changed = True
            continue

        previous = mtime_cache.get(key)
        if previous != current:
            mtime_cache[key] = current
            is_changed = True
            if previous is None:
                log.debug(f"New file detected: {file_path}")
            else:
                log.debug(f"File changed: {file_path}")

    # Detect removed files
    removed_keys = set(mtime_cache.keys()) - current_keys
    for key in removed_keys:
        del mtime_cache[key]
        is_changed = True
        log.debug(f"File removed: {key}")

    return is_changed


def _require_env(name: str) -> str:
    """Read a required environment variable, exiting if unset."""
    value = os.environ.get(name, "")
    if not value:
        print(f"ERROR: {name} must be set", file=sys.stderr)
        sys.exit(1)
    return value


# --- WATCHDOG-DEPENDENT CODE BELOW (not importable without watchdog) ---


class _ChangeHandler(FileSystemEventHandler):
    """Watchdog handler that signals the main loop on any filesystem change."""

    def __init__(self, wake_event: threading.Event) -> None:
        super().__init__()
        self._wake_event = wake_event

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._wake_event.set()


def _setup_watchdog(
    watch_paths: list[Path],
    wake_event: threading.Event,
    log: _Logger,
) -> tuple[Observer, bool]:
    """Create and start a watchdog Observer for the parent directories of watched files.

    Returns (observer, is_active). If the observer fails to start,
    is_active is False and the caller should fall back to polling only.
    """
    handler = _ChangeHandler(wake_event)
    observer = Observer()

    # Watch the parent directories of the files we care about
    watched_dirs: set[str] = set()
    for file_path in watch_paths:
        parent = str(file_path.parent)
        if parent not in watched_dirs:
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                observer.schedule(handler, parent, recursive=False)
                watched_dirs.add(parent)
            except Exception as exc:
                log.info(f"WARNING: failed to watch {parent}: {exc}")

    try:
        observer.start()
        return observer, True
    except Exception as exc:
        log.info(f"WARNING: watchdog observer failed to start, falling back to polling only: {exc}")
        return observer, False


def _run_sync_loop(
    db_path: Path,
    conversations_file: Path,
    messages_file: Path,
    watch_paths: list[Path],
    poll_interval: int,
    wake_event: threading.Event,
    log: _Logger,
) -> None:
    """Run the main sync loop: wait for watchdog or poll timeout, then sync."""
    mtime_cache: dict[str, tuple[float, int]] = {}
    _mtime_poll(watch_paths, mtime_cache, log)

    while True:
        is_triggered_by_watchdog = wake_event.wait(timeout=poll_interval)
        wake_event.clear()

        if is_triggered_by_watchdog:
            log.debug("Woken by watchdog filesystem event")

        # Always update the mtime cache so it stays in sync
        is_mtime_changed = _mtime_poll(watch_paths, mtime_cache, log)
        if not is_triggered_by_watchdog and is_mtime_changed:
            log.info("Periodic mtime poll detected changes")

        synced_count = _sync_messages(db_path, conversations_file, messages_file, log)
        if synced_count > 0:
            log.info(f"Synced {synced_count} new message event(s) -> logs/messages/events.jsonl")
        else:
            log.debug("No new messages to sync")


def main() -> None:
    agent_state_dir = Path(_require_env("MNG_AGENT_STATE_DIR"))
    host_dir = Path(_require_env("MNG_HOST_DIR"))

    conversations_file = agent_state_dir / "logs" / "conversations" / "events.jsonl"
    messages_file = agent_state_dir / "logs" / "messages" / "events.jsonl"
    messages_file.parent.mkdir(parents=True, exist_ok=True)

    log = _Logger(host_dir / "logs" / "conversation_watcher.log")

    settings = _load_watcher_settings(agent_state_dir)
    db_path = _get_llm_db_path()

    log.info("Conversation watcher started")
    log.info(f"  Agent data dir: {agent_state_dir}")
    log.info(f"  LLM database: {db_path}")
    log.info(f"  Conversations events: {conversations_file}")
    log.info(f"  Messages events: {messages_file}")
    log.info(f"  Log file: {log.log_file_path}")
    log.info(f"  Poll interval: {settings.poll_interval}s")
    log.info("  Using watchdog for file watching with periodic mtime polling")

    # Watch the llm database and the conversations events file
    watch_paths = [db_path, conversations_file]

    wake_event = threading.Event()
    observer, is_watchdog_active = _setup_watchdog(watch_paths, wake_event, log)

    try:
        _run_sync_loop(
            db_path, conversations_file, messages_file, watch_paths, settings.poll_interval, wake_event, log
        )
    except KeyboardInterrupt:
        log.info("Conversation watcher stopping (KeyboardInterrupt)")
    finally:
        if is_watchdog_active:
            observer.stop()
            observer.join()


if __name__ == "__main__":
    main()
