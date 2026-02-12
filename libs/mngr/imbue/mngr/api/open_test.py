"""Unit tests for the open API module."""

import json
import threading
from datetime import datetime
from datetime import timezone
from pathlib import Path
from uuid import uuid4

import pytest

from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.api.open import _record_activity_loop
from imbue.mngr.api.open import open_agent_url
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.errors import UserInputError
from imbue.mngr.hosts.host import Host
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.polling import wait_for


def _create_test_agent(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
    reported_url: str | None = None,
) -> BaseAgent:
    """Create a real BaseAgent on a local host for testing open_agent_url."""
    host = local_provider.create_host(HostName("test"))
    assert isinstance(host, Host)

    agent_id = AgentId(f"agent-{uuid4().hex}")
    agent_name = AgentName(f"test-agent-{uuid4().hex[:8]}")

    # Create agent directory and data.json
    agent_dir = temp_host_dir / "agents" / str(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "id": str(agent_id),
        "name": str(agent_name),
        "type": "test",
        "command": "sleep 1000",
        "work_dir": str(temp_work_dir),
        "create_time": datetime.now(timezone.utc).isoformat(),
        "start_on_boot": False,
    }
    (agent_dir / "data.json").write_text(json.dumps(data, indent=2))

    # Write the reported URL if provided
    if reported_url is not None:
        status_dir = agent_dir / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        (status_dir / "url").write_text(reported_url)

    return BaseAgent(
        id=agent_id,
        name=agent_name,
        agent_type=AgentTypeName("test"),
        work_dir=temp_work_dir,
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        host=host,
        mngr_ctx=local_provider.mngr_ctx,
        agent_config=AgentTypeConfig(command=CommandString("sleep 1000")),
    )


def test_open_agent_url_opens_browser(
    monkeypatch: pytest.MonkeyPatch,
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that open_agent_url opens the reported URL in a browser."""
    opened_urls: list[str] = []
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: opened_urls.append(url))

    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/agent")
    open_agent_url(agent=agent, is_wait=False, is_active=False)

    assert len(opened_urls) == 1
    assert opened_urls[0] == "https://example.com/agent"


def test_open_agent_url_raises_when_no_url(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that open_agent_url raises UserInputError when agent has no URL."""
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir, reported_url=None)

    with pytest.raises(UserInputError, match="has no URL"):
        open_agent_url(agent=agent, is_wait=False, is_active=False)


def test_open_agent_url_wait_exits_when_stop_event_set(
    monkeypatch: pytest.MonkeyPatch,
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that --wait blocks until the stop event is set."""
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: None)

    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/agent")

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
    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir)
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
    monkeypatch: pytest.MonkeyPatch,
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that --active causes activity to be recorded while waiting."""
    monkeypatch.setattr("imbue.mngr.api.open.webbrowser.open", lambda url: None)

    agent = _create_test_agent(local_provider, temp_host_dir, temp_work_dir, reported_url="https://example.com/agent")

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
