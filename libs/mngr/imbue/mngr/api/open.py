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


def _resolve_agent_url(agent: AgentInterface, url_type: str | None) -> str:
    """Resolve the URL to open for an agent, optionally filtered by type.

    When url_type is None, returns the default URL (from get_reported_url).
    When url_type is specified, looks it up in get_reported_urls().
    """
    if url_type is None:
        # Try the legacy single-URL first, then fall back to the first typed URL
        url = agent.get_reported_url()
        if url is not None:
            return url
        reported_urls = agent.get_reported_urls()
        if reported_urls:
            return next(iter(reported_urls.values()))
        raise UserInputError(
            f"Agent '{agent.name}' has no URL. The agent may not have reported a URL yet, or it may not support URLs."
        )

    reported_urls = agent.get_reported_urls()
    if not reported_urls:
        raise UserInputError(
            f"Agent '{agent.name}' has no URLs. "
            "The agent may not have reported any URLs yet, or it may not support URLs."
        )

    if url_type not in reported_urls:
        available_types = ", ".join(sorted(reported_urls.keys()))
        raise UserInputError(
            f"Agent '{agent.name}' has no URL of type '{url_type}'. Available types: {available_types}"
        )

    return reported_urls[url_type]


def open_agent_url(
    agent: AgentInterface,
    is_wait: bool,
    is_active: bool,
    url_type: str | None = None,
    # Injectable for testing; production callers should omit these
    stop_event: threading.Event | None = None,
    activity_interval_seconds: float = _ACTIVITY_INTERVAL_SECONDS,
) -> None:
    """Open an agent's URL in the default web browser.

    Raises UserInputError if the agent has no reported URL (or no URL of the
    requested type).
    """
    url = _resolve_agent_url(agent, url_type)

    logger.info("Opening URL for agent {}: {}", agent.name, url)
    webbrowser.open(url)

    if not is_wait:
        return

    logger.info("Waiting (press Ctrl+C to exit)...")

    resolved_stop_event = stop_event if stop_event is not None else threading.Event()

    if is_active:
        activity_thread = threading.Thread(
            target=_record_activity_loop,
            args=(agent, resolved_stop_event),
            kwargs={"activity_interval_seconds": activity_interval_seconds},
            daemon=True,
        )
        activity_thread.start()

    try:
        while not resolved_stop_event.wait(timeout=1.0):
            pass
    except KeyboardInterrupt:
        logger.info("Exiting")
    finally:
        resolved_stop_event.set()


def _record_activity_loop(
    agent: AgentInterface,
    stop_event: threading.Event,
    # Injectable interval for testing; production callers should omit this
    activity_interval_seconds: float = _ACTIVITY_INTERVAL_SECONDS,
) -> None:
    """Periodically record user activity until stop_event is set."""
    while not stop_event.wait(timeout=activity_interval_seconds):
        try:
            agent.record_activity(ActivitySource.USER)
            logger.debug("Recorded user activity for agent {}", agent.name)
        except (OSError, BaseMngrError):
            logger.debug("Failed to record activity for agent {}", agent.name)
