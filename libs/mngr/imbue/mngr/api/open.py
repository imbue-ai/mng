import threading
import webbrowser
from typing import Final

from loguru import logger

from imbue.mngr.errors import BaseMngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.primitives import ActivitySource

# How often to record user activity when --active is used (seconds)
_ACTIVITY_INTERVAL_SECONDS: Final[float] = 30.0


def open_agent_url(
    agent: AgentInterface,
    is_wait: bool,
    is_active: bool,
) -> None:
    """Open an agent's URL in the default web browser.

    Raises UserInputError if the agent has no reported URL.
    """
    url = agent.get_reported_url()
    if url is None:
        raise UserInputError(
            f"Agent '{agent.name}' has no URL. The agent may not have reported a URL yet, or it may not support URLs."
        )

    logger.info("Opening URL for agent {}: {}", agent.name, url)
    webbrowser.open(url)

    if not is_wait:
        return

    logger.info("Waiting (press Ctrl+C to exit)...")

    stop_event = threading.Event()

    if is_active:
        activity_thread = threading.Thread(
            target=_record_activity_loop,
            args=(agent, stop_event),
            daemon=True,
        )
        activity_thread.start()

    try:
        while not stop_event.wait(timeout=1.0):
            pass
    except KeyboardInterrupt:
        logger.info("Exiting")
    finally:
        stop_event.set()


def _record_activity_loop(agent: AgentInterface, stop_event: threading.Event) -> None:
    """Periodically record user activity until stop_event is set."""
    while not stop_event.wait(timeout=_ACTIVITY_INTERVAL_SECONDS):
        try:
            agent.record_activity(ActivitySource.USER)
            logger.debug("Recorded user activity for agent {}", agent.name)
        except (OSError, BaseMngrError):
            logger.debug("Failed to record activity for agent {}", agent.name)
