import json
import threading
from pathlib import Path

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.config.data_types import MngContext
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.notifier import Notifier
from imbue.mng_notifications.notifier import build_execute_command


def watch_for_waiting_agents(
    mng_ctx: MngContext,
    plugin_config: NotificationsPluginConfig,
    notifier: Notifier,
    stop_event: threading.Event | None = None,
) -> None:
    """Watch agent event files for RUNNING -> WAITING transitions and send notifications.

    Monitors all agent state directories under the host dir for
    agent_state_transition events. Runs until stop_event is set or interrupted.
    """
    if stop_event is None:
        stop_event = threading.Event()

    agents_dir = mng_ctx.config.default_host_dir / "agents"
    logger.info("Watching for agent state transitions in {}", agents_dir)

    tracked_sizes: dict[Path, int] = {}

    while not stop_event.is_set():
        event_files = _find_agent_event_files(agents_dir)

        for event_file in event_files:
            new_content = _read_new_content(event_file, tracked_sizes)
            if new_content:
                _process_events(
                    new_content,
                    plugin_config,
                    notifier,
                    mng_ctx.concurrency_group,
                )

        stop_event.wait(timeout=1.0)


def _find_agent_event_files(agents_dir: Path) -> list[Path]:
    """Find all mng_agents event files across agent state directories."""
    if not agents_dir.exists():
        return []
    return list(agents_dir.glob("*/events/mng_agents/events.jsonl"))


def _read_new_content(event_file: Path, tracked_sizes: dict[Path, int]) -> str:
    """Read any new content appended to an event file since last check."""
    try:
        current_size = event_file.stat().st_size
    except OSError:
        return ""

    last_size = tracked_sizes.get(event_file, 0)
    if current_size <= last_size:
        tracked_sizes[event_file] = current_size
        return ""

    try:
        with event_file.open() as f:
            f.seek(last_size)
            new_content = f.read()
    except OSError:
        return ""

    tracked_sizes[event_file] = current_size
    return new_content


def _process_events(
    content: str,
    plugin_config: NotificationsPluginConfig,
    notifier: Notifier,
    cg: ConcurrencyGroup,
) -> None:
    """Parse JSONL content and send notifications for RUNNING -> WAITING transitions."""
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if event.get("type") != "agent_state_transition":
            continue
        if event.get("from_state") != "RUNNING" or event.get("to_state") != "WAITING":
            continue

        agent_name = event.get("agent_name", "unknown")
        agent_id = event.get("agent_id", "unknown")
        logger.info("{} ({}): RUNNING -> WAITING", agent_name, agent_id)

        title = "Agent waiting"
        message = f"{agent_name} is waiting for input"
        execute_command = build_execute_command(agent_name, plugin_config)
        notifier.notify(title, message, execute_command, cg)
