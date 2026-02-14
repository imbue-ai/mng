"""Unit tests for the open API module."""

import threading
from pathlib import Path

import pytest

from imbue.mngr.api.open import _record_activity_loop
from imbue.mngr.api.open import _resolve_agent_url
from imbue.mngr.api.open import open_agent_url
from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.errors import UserInputError
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.polling import wait_for

# Prevent all tests in this module from opening a real browser.
# Each test that calls open_agent_url (with a URL) needs this.
_intercepted_urls: list[str] = []


@pytest.fixture(autouse=True)
def _suppress_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Intercept webbrowser.open to prevent browser launches during tests."""
    _intercepted_urls.clear()
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: _intercepted_urls.append(url))


def test_open_agent_url_opens_browser(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that open_agent_url opens the reported URL in a browser."""
    agent = create_test_base_agent(
        local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/agent"
    )
    open_agent_url(agent=agent, is_wait=False, is_active=False)

    assert len(_intercepted_urls) == 1
    assert _intercepted_urls[0] == "https://example.com/agent"


def test_open_agent_url_raises_when_no_url(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that open_agent_url raises UserInputError when agent has no URL."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir, reported_url=None)

    with pytest.raises(UserInputError, match="has no URL"):
        open_agent_url(agent=agent, is_wait=False, is_active=False)


def test_open_agent_url_wait_exits_when_stop_event_set(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that --wait blocks until the stop event is set."""
    agent = create_test_base_agent(
        local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/agent"
    )

    # Pre-set the stop event so the wait loop exits immediately
    stop_event = threading.Event()
    stop_event.set()

    open_agent_url(agent=agent, is_wait=True, is_active=False, stop_event=stop_event)


def test_record_activity_loop_records_until_stopped(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _record_activity_loop records activity until stop_event is set."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    stop_event = threading.Event()

    # Run the loop in a thread with a short interval
    thread = threading.Thread(
        target=_record_activity_loop,
        args=(agent, stop_event),
        kwargs={"activity_interval_seconds": 0.01},
        daemon=True,
    )
    thread.start()

    # The activity file is written to the agent's activity directory
    activity_path = temp_host_dir / "agents" / str(agent.id) / "activity" / "user"

    # Poll until at least one recording has been made
    wait_for(
        condition=lambda: activity_path.exists(),
        timeout=5.0,
        poll_interval=0.01,
        error_message="Expected activity file to be created",
    )

    stop_event.set()
    thread.join(timeout=1.0)

    assert activity_path.exists()


def test_open_agent_url_active_records_activity(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that --active causes activity to be recorded while waiting."""
    agent = create_test_base_agent(
        local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/agent"
    )

    stop_event = threading.Event()
    activity_path = temp_host_dir / "agents" / str(agent.id) / "activity" / "user"

    # Run open_agent_url in a background thread with a short activity interval
    open_thread = threading.Thread(
        target=open_agent_url,
        kwargs={
            "agent": agent,
            "is_wait": True,
            "is_active": True,
            "stop_event": stop_event,
            "activity_interval_seconds": 0.01,
        },
        daemon=True,
    )
    open_thread.start()

    # Wait for activity to be recorded
    wait_for(
        condition=lambda: activity_path.exists(),
        timeout=5.0,
        poll_interval=0.01,
        error_message="Expected activity to be recorded",
    )

    # Signal the function to stop
    stop_event.set()
    open_thread.join(timeout=2.0)

    assert activity_path.exists()


# =============================================================================
# URL type resolution tests
# =============================================================================


def test_resolve_agent_url_returns_default_when_no_type(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    agent = create_test_base_agent(
        local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/default"
    )
    url = _resolve_agent_url(agent, url_type=None)
    assert url == "https://example.com/default"


def test_resolve_agent_url_returns_typed_url(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_url="https://example.com/default",
        reported_urls={"terminal": "https://example.com/ttyd"},
    )
    url = _resolve_agent_url(agent, url_type="terminal")
    assert url == "https://example.com/ttyd"


def test_resolve_agent_url_raises_for_unknown_type(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_url="https://example.com/default",
        reported_urls={"terminal": "https://example.com/ttyd"},
    )
    with pytest.raises(UserInputError, match="no URL of type 'chat'"):
        _resolve_agent_url(agent, url_type="chat")


def test_resolve_agent_url_shows_available_types_in_error(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_url="https://example.com/default",
        reported_urls={"terminal": "https://example.com/ttyd"},
    )
    with pytest.raises(UserInputError, match="Available types: default, terminal"):
        _resolve_agent_url(agent, url_type="nonexistent")


def test_resolve_agent_url_raises_when_no_urls_and_type_requested(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir, reported_url=None)
    with pytest.raises(UserInputError, match="has no URLs"):
        _resolve_agent_url(agent, url_type="terminal")


def test_open_agent_url_with_type_opens_typed_url(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    agent = create_test_base_agent(
        local_provider,
        temp_host_dir,
        temp_work_dir,
        reported_url="https://example.com/default",
        reported_urls={"terminal": "https://example.com/ttyd"},
    )
    open_agent_url(agent=agent, is_wait=False, is_active=False, url_type="terminal", open_url=_capture_url)

    assert len(_intercepted_urls) == 1
    assert _intercepted_urls[0] == "https://example.com/ttyd"
