"""Shared test fixtures for API tests."""

import subprocess
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence

from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId


class FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface.

    Only implements work_dir, which is all the sync functions actually use.
    """

    work_dir: Path = Field(description="Working directory for this agent")


class FakeHost(MutableModel):
    """Minimal test double for OnlineHostInterface.

    Implements execute_command and is_local. Executes commands locally via subprocess.
    Set is_local=False to simulate a remote host.
    """

    is_local: bool = Field(default=True, description="Whether this is a local host")

    def execute_command(
        self,
        command: str,
        cwd: Path | None = None,
    ) -> CommandResult:
        """Execute a shell command locally and return the result."""
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            success=result.returncode == 0,
        )


class StubAgent(AgentInterface):
    """Full AgentInterface implementation for integration testing.

    Implements all abstract methods with stub/no-op implementations.
    """

    def get_host(self) -> OnlineHostInterface:
        raise NotImplementedError

    def assemble_command(
        self,
        host: OnlineHostInterface,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString:
        return CommandString("test")

    def get_command(self) -> CommandString:
        return CommandString("test")

    def get_permissions(self) -> list[Any]:
        return []

    def set_permissions(self, value: Any) -> None:
        pass

    def get_is_start_on_boot(self) -> bool:
        return False

    def set_is_start_on_boot(self, value: bool) -> None:
        pass

    def is_running(self) -> bool:
        return True

    def get_lifecycle_state(self) -> AgentLifecycleState:
        return AgentLifecycleState.RUNNING

    def get_initial_message(self) -> str | None:
        return None

    def get_resume_message(self) -> str | None:
        return None

    def get_message_delay_seconds(self) -> float:
        return 1.0

    def send_message(self, message: str) -> None:
        pass

    def get_reported_url(self) -> str | None:
        return None

    def get_reported_start_time(self) -> datetime | None:
        return None

    def get_reported_status_markdown(self) -> str | None:
        return None

    def get_reported_status_html(self) -> str | None:
        return None

    def get_reported_status(self) -> Any:
        return None

    def get_reported_activity_time(self, activity_type: Any) -> datetime | None:
        return None

    def record_activity(self, activity_type: Any) -> None:
        pass

    def get_reported_activity_record(self, activity_type: Any) -> str | None:
        return None

    def get_plugin_data(self, plugin_name: str) -> dict[str, Any]:
        return {}

    def set_plugin_data(self, plugin_name: str, data: dict[str, Any]) -> None:
        pass

    def get_reported_plugin_file(self, plugin_name: str, filename: str) -> str:
        return ""

    def set_reported_plugin_file(self, plugin_name: str, filename: str, data: str) -> None:
        pass

    def list_reported_plugin_files(self, plugin_name: str) -> list[str]:
        return []

    def get_env_vars(self) -> dict[str, str]:
        return {}

    def set_env_vars(self, env: Any) -> None:
        pass

    def get_env_var(self, key: str) -> str | None:
        return None

    def set_env_var(self, key: str, value: str) -> None:
        pass

    @property
    def runtime_seconds(self) -> float | None:
        return None

    def on_before_provisioning(self, host: Any, options: Any, mngr_ctx: Any) -> None:
        pass

    def get_provision_file_transfers(self, host: Any, options: Any, mngr_ctx: Any) -> Any:
        return []

    def provision(self, host: Any, options: Any, mngr_ctx: Any) -> None:
        pass

    def on_after_provisioning(self, host: Any, options: Any, mngr_ctx: Any) -> None:
        pass


def create_test_agent(
    agent_id: AgentId,
    agent_name: AgentName,
    host_id: HostId,
    mngr_ctx: MngrContext,
) -> StubAgent:
    """Create a StubAgent with the given parameters."""
    return StubAgent(
        id=agent_id,
        name=agent_name,
        agent_type=AgentTypeName("test"),
        work_dir=Path("/tmp"),
        create_time=datetime.now(timezone.utc),
        host_id=host_id,
        mngr_ctx=mngr_ctx,
        agent_config=AgentTypeConfig(),
    )


class StubHost(Host):
    """Host subclass for testing.

    Allows using real Host instances in tests without needing
    actual pyinfra connectors or providers.
    """

    _test_agents: list[AgentInterface]

    def get_agents(self) -> list[AgentInterface]:
        """Return the test agents configured for this host."""
        return self._test_agents


class StubPyinfraConnector:
    """Minimal PyinfraConnector replacement for testing."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def connector_cls_name(self) -> str:
        return "TestConnector"


class StubProviderInstance(ProviderInstanceInterface):
    """Minimal ProviderInstanceInterface for testing."""

    @property
    def is_authorized(self) -> bool:
        return True

    @property
    def supports_snapshots(self) -> bool:
        return False

    @property
    def supports_shutdown_hosts(self) -> bool:
        return True

    @property
    def supports_volumes(self) -> bool:
        return False

    @property
    def supports_mutable_tags(self) -> bool:
        return True

    def list_hosts(self, include_destroyed: bool = False, cg: ConcurrencyGroup | None = None) -> list[HostInterface]:
        return []

    def get_host(self, host: HostId | HostName) -> HostInterface:
        raise NotImplementedError

    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
        lifecycle: HostLifecycleOptions | None = None,
        known_hosts: Sequence[str] | None = None,
    ) -> OnlineHostInterface:
        raise NotImplementedError

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> OnlineHostInterface:
        raise NotImplementedError

    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        pass

    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        pass

    def on_connection_error(self, host_id: HostId) -> None:
        pass

    def list_snapshots(self, host: HostInterface | HostId) -> list[SnapshotInfo]:
        return []

    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        raise NotImplementedError

    def delete_snapshot(self, host: HostInterface | HostId, snapshot_id: SnapshotId) -> None:
        pass

    def get_host_resources(self, host: HostInterface) -> HostResources:
        raise NotImplementedError

    def get_host_tags(self, host: HostInterface | HostId) -> dict[str, str]:
        return {}

    def set_host_tags(self, host: HostInterface | HostId, tags: Mapping[str, str]) -> None:
        pass

    def add_tags_to_host(self, host: HostInterface | HostId, tags: Mapping[str, str]) -> None:
        pass

    def remove_tags_from_host(self, host: HostInterface | HostId, keys: Sequence[str]) -> None:
        pass

    def persist_agent_data(self, host_id: HostId, agent_data: Mapping[str, object]) -> None:
        pass

    def remove_persisted_agent_data(self, host_id: HostId, agent_id: AgentId) -> None:
        pass

    def list_persisted_agent_data_for_host(self, host_id: HostId) -> list[dict[str, Any]]:
        return []

    def list_volumes(self) -> list[VolumeInfo]:
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        pass

    def rename_host(self, host: HostInterface | HostId, name: HostName) -> HostInterface:
        raise NotImplementedError

    def get_connector(self, host: HostInterface | HostId) -> Any:
        raise NotImplementedError


def create_test_host(
    host_id: HostId,
    connector_name: str,
    agents: list[AgentInterface],
    mngr_ctx: MngrContext,
    host_dir: Path,
) -> StubHost:
    """Create a StubHost using model_construct to bypass validation."""
    provider = StubProviderInstance.model_construct(
        name=ProviderInstanceName("test"),
        host_dir=host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = StubHost.model_construct(
        id=host_id,
        connector=StubPyinfraConnector(connector_name),
        provider_instance=provider,
        mngr_ctx=mngr_ctx,
        _test_agents=agents,
    )
    return host
