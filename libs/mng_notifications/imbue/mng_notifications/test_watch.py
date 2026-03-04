"""Acceptance test for the watch command's state transition detection.

Creates a real agent on a local host, manipulates its active file to
simulate RUNNING -> WAITING, and verifies the watcher detects it.
"""

import threading
from pathlib import Path
from typing import Any

import pytest

from imbue.mng.api.list import ListResult
from imbue.mng.api.list import list_agents as real_list_agents
from imbue.mng.config.data_types import MngContext
from imbue.mng.hosts.host import Host
from imbue.mng.interfaces.host import CreateAgentOptions
from imbue.mng.primitives import AgentLifecycleState
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import CommandString
from imbue.mng.primitives import HostName
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.utils.polling import wait_for
from imbue.mng_notifications.config import NotificationsPluginConfig
from imbue.mng_notifications.mock_notifier_test import RecordingNotifier
from imbue.mng_notifications.testing import patch_list_agents
from imbue.mng_notifications.watcher import watch_for_waiting_agents


@pytest.mark.tmux
@pytest.mark.acceptance
def test_watcher_detects_running_to_waiting_transition(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    tmp_path: Path,
    temp_mng_ctx: MngContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a real agent, simulate RUNNING -> WAITING via the active file,
    and verify the watcher sends a notification."""
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

    agent_state_dir = temp_host_dir / "agents" / str(agent.id)
    active_file = agent_state_dir / "active"
    active_file.touch()

    wait_for(
        lambda: agent.get_lifecycle_state() == AgentLifecycleState.RUNNING,
        timeout=5,
        error_message="Agent did not reach RUNNING state",
    )

    # Wrap list_agents to signal when the initial poll completes
    polled_event = threading.Event()

    def signaling_list_agents(mng_ctx: Any, **kwargs: Any) -> ListResult:
        result = real_list_agents(mng_ctx, **kwargs)
        polled_event.set()
        return result

    patch_list_agents(monkeypatch, signaling_list_agents)

    notifier = RecordingNotifier()
    stop_event = threading.Event()

    watcher_thread = threading.Thread(
        target=watch_for_waiting_agents,
        kwargs={
            "mng_ctx": temp_mng_ctx,
            "interval_seconds": 0.5,
            "include_filters": (),
            "exclude_filters": (),
            "plugin_config": NotificationsPluginConfig(),
            "notifier": notifier,
            "stop_event": stop_event,
        },
    )
    watcher_thread.start()

    try:
        polled_event.wait(timeout=5)

        active_file.unlink()

        wait_for(
            lambda: len(notifier.calls) > 0,
            timeout=5,
            poll_interval=0.3,
            error_message="Watcher did not send notification for RUNNING -> WAITING",
        )

        assert notifier.calls[0][0] == "Agent waiting"
        assert "watch-test" in notifier.calls[0][1]
    finally:
        stop_event.set()
        watcher_thread.join(timeout=5)
        host.stop_agents([agent.id], timeout_seconds=3.0)
