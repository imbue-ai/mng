"""Unit tests for the open API module."""

import threading
from unittest.mock import MagicMock

import pytest

from imbue.mngr.api.open import _record_activity_loop
from imbue.mngr.api.open import open_agent_url
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import AgentName
from imbue.mngr.utils.polling import wait_for

# Save the original Event class before any monkeypatching
_OriginalEvent = threading.Event


def _make_mock_agent(url: str | None = None) -> MagicMock:
    """Create a mock agent with an optional reported URL."""
    agent = MagicMock()
    agent.name = AgentName("test-agent")
    agent.get_reported_url.return_value = url
    return agent


def _make_interrupting_event(interrupt_after_count: int = 2) -> threading.Event:
    """Create an Event whose wait() raises KeyboardInterrupt after N calls."""
    event = _OriginalEvent()
    call_count = 0
    original_wait = event.wait

    def interrupting_wait(timeout: float | None = None) -> bool:
        nonlocal call_count
        call_count += 1
        if call_count >= interrupt_after_count:
            raise KeyboardInterrupt
        # Brief wait to allow other threads to run
        return original_wait(timeout=0.01)

    event.wait = interrupting_wait  # ty: ignore[invalid-assignment]
    return event


def test_open_agent_url_opens_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that open_agent_url opens the reported URL in a browser."""
    opened_urls: list[str] = []
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: opened_urls.append(url))

    agent = _make_mock_agent(url="https://example.com/agent")
    open_agent_url(agent=agent, is_wait=False, is_active=False)

    assert len(opened_urls) == 1
    assert opened_urls[0] == "https://example.com/agent"


def test_open_agent_url_raises_when_no_url() -> None:
    """Test that open_agent_url raises UserInputError when agent has no URL."""
    agent = _make_mock_agent(url=None)

    with pytest.raises(UserInputError, match="has no URL"):
        open_agent_url(agent=agent, is_wait=False, is_active=False)


def test_open_agent_url_wait_blocks_until_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that --wait causes the function to block until KeyboardInterrupt."""
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: None)

    agent = _make_mock_agent(url="https://example.com/agent")

    monkeypatch.setattr(
        "imbue.mngr.api.open.threading.Event",
        lambda: _make_interrupting_event(interrupt_after_count=2),
    )

    # Should not raise -- KeyboardInterrupt is caught internally
    open_agent_url(agent=agent, is_wait=True, is_active=False)


def test_record_activity_loop_records_until_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that _record_activity_loop records activity until stop_event is set."""
    monkeypatch.setattr("imbue.mngr.api.open._ACTIVITY_INTERVAL_SECONDS", 0.01)

    agent = _make_mock_agent()
    stop_event = _OriginalEvent()

    # Run the loop in a thread, let it record a few times, then stop it
    thread = threading.Thread(target=_record_activity_loop, args=(agent, stop_event), daemon=True)
    thread.start()

    # Poll until at least one recording has been made
    wait_for(
        condition=lambda: agent.record_activity.call_count >= 1,
        timeout=5.0,
        poll_interval=0.01,
        error_message="Expected at least one record_activity call",
    )

    stop_event.set()
    thread.join(timeout=1.0)

    assert agent.record_activity.call_count >= 1


def test_open_agent_url_active_starts_activity_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that --active starts the activity recording thread."""
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: None)

    agent = _make_mock_agent(url="https://example.com/agent")

    # Track whether _record_activity_loop was called
    activity_loop_called = _OriginalEvent()

    def tracking_activity_loop(agent: MagicMock, stop_event: threading.Event) -> None:
        activity_loop_called.set()

    monkeypatch.setattr("imbue.mngr.api.open._record_activity_loop", tracking_activity_loop)

    # Create an event that interrupts after enough wait() calls to allow the
    # activity thread to start (interrupt_after_count=3 gives the thread time)
    monkeypatch.setattr(
        "imbue.mngr.api.open.threading.Event",
        lambda: _make_interrupting_event(interrupt_after_count=3),
    )

    open_agent_url(agent=agent, is_wait=True, is_active=True)

    assert activity_loop_called.is_set()
