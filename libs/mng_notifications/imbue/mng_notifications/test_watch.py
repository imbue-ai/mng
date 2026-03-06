import json
import threading
from pathlib import Path

import pytest

from imbue.mng.config.data_types import MngContext
from imbue.mng.hosts.host import Host
from imbue.mng.interfaces.host import CreateAgentOptions
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import HostName
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.utils.polling import wait_for
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.mock_notifier_test import RecordingNotifier
from imbue.mng_notifications.watcher import watch_for_waiting_agents


@pytest.mark.tmux
@pytest.mark.acceptance
def test_watcher_detects_running_to_waiting_via_event(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    tmp_path: Path,
    temp_mng_ctx: MngContext,
) -> None:
    """Create a real agent, write a state transition event, and verify the watcher sends a notification."""
    host = local_provider.create_host(HostName("localhost"))
    assert isinstance(host, Host)

    work_dir = tmp_path / "work_dir"
    work_dir.mkdir()

    agent = host.create_agent_state(
        work_dir_path=work_dir,
        options=CreateAgentOptions(
            name=AgentName("watch-test"),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 1000"),
        ),
    )
    host.start_agents([agent.id])

    notifier = RecordingNotifier()
    stop_event = threading.Event()

    watcher_thread = threading.Thread(
        target=watch_for_waiting_agents,
        kwargs={
            "mng_ctx": temp_mng_ctx,
            "plugin_config": NotificationsPluginConfig(),
            "notifier": notifier,
            "stop_event": stop_event,
        },
    )
    watcher_thread.start()

    try:
        # Write a RUNNING -> WAITING transition event to the agent's event file
        events_dir = temp_host_dir / "agents" / str(agent.id) / "events" / "mng_agents"
        events_dir.mkdir(parents=True, exist_ok=True)
        event_file = events_dir / "events.jsonl"
        event = json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "agent_state_transition",
                "event_id": "evt-test123",
                "source": "mng_agents",
                "agent_id": str(agent.id),
                "agent_name": str(agent.name),
                "from_state": "RUNNING",
                "to_state": "WAITING",
            }
        )
        event_file.write_text(event + "\n")

        wait_for(
            lambda: len(notifier.calls) > 0,
            timeout=5,
            poll_interval=0.3,
            error_message="Watcher did not send notification for RUNNING -> WAITING event",
        )

        assert notifier.calls[0][0] == "Agent waiting"
        assert "watch-test" in notifier.calls[0][1]
    finally:
        stop_event.set()
        watcher_thread.join(timeout=5)
        host.stop_agents([agent.id], timeout_seconds=3.0)
