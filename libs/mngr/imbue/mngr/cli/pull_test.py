"""Unit tests for pull CLI command."""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.pull import PullResult
from imbue.mngr.cli.pull import PullCliOptions
from imbue.mngr.cli.pull import _output_result
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.main import cli
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId


class _TestAgent(AgentInterface):
    """Minimal agent implementation for testing."""

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


def _create_test_agent(agent_id: AgentId, agent_name: AgentName, host_id: HostId, mngr_ctx: MngrContext) -> _TestAgent:
    """Create a test agent with the given parameters."""
    return _TestAgent(
        id=agent_id,
        name=agent_name,
        agent_type=AgentTypeName("test"),
        work_dir=Path("/tmp"),
        create_time=datetime.now(timezone.utc),
        host_id=host_id,
        mngr_ctx=mngr_ctx,
        agent_config=AgentTypeConfig(),
    )


class _TestHost(Host):
    """Minimal Host subclass for testing.

    This allows using real Host instances in tests without needing
    actual pyinfra connectors or providers.
    """

    _test_agents: list[AgentInterface]

    def get_agents(self) -> list[AgentInterface]:
        """Return the test agents configured for this host."""
        return self._test_agents


class _TestPyinfraConnector:
    """Minimal PyinfraConnector replacement for testing."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def connector_cls_name(self) -> str:
        return "TestConnector"


class _TestProviderInstance(ProviderInstanceInterface):
    """Minimal ProviderInstanceInterface for testing."""

    @property
    def is_authorized(self) -> bool:
        return True

    @property
    def supports_snapshots(self) -> bool:
        return False

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


def _create_test_host(
    host_id: HostId,
    connector_name: str,
    agents: list[AgentInterface],
    mngr_ctx: MngrContext,
    host_dir: Path,
) -> _TestHost:
    """Create a test host using model_construct to bypass validation."""
    provider = _TestProviderInstance.model_construct(
        name=ProviderInstanceName("test"),
        host_dir=host_dir,
        mngr_ctx=mngr_ctx,
    )
    host = _TestHost.model_construct(
        id=host_id,
        connector=_TestPyinfraConnector(connector_name),
        provider_instance=provider,
        mngr_ctx=mngr_ctx,
        _test_agents=agents,
    )
    return host


def test_pull_cli_options_has_all_fields() -> None:
    """Test that PullCliOptions has all expected fields."""
    assert hasattr(PullCliOptions, "__annotations__")
    annotations = PullCliOptions.__annotations__
    assert "source" in annotations
    assert "source_agent" in annotations
    assert "source_host" in annotations
    assert "source_path" in annotations
    assert "destination" in annotations
    assert "dry_run" in annotations
    assert "stop" in annotations
    assert "delete" in annotations
    assert "sync_mode" in annotations
    assert "exclude" in annotations


def test_pull_command_is_registered() -> None:
    """Test that pull command is registered in the CLI group."""
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--help"])
    assert result.exit_code == 0
    assert "Pull files from an agent" in result.output


def test_pull_command_help_shows_options() -> None:
    """Test that pull --help shows all options."""
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--help"])
    assert result.exit_code == 0
    assert "--source-agent" in result.output
    assert "--source-path" in result.output
    assert "--destination" in result.output
    assert "--dry-run" in result.output
    assert "--stop" in result.output
    assert "--delete" in result.output
    assert "--sync-mode" in result.output
    assert "--exclude" in result.output


def test_pull_command_sync_mode_choices() -> None:
    """Test that sync-mode shows valid choices."""
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--help"])
    assert result.exit_code == 0
    assert "files" in result.output
    assert "state" in result.output
    assert "full" in result.output


def test_output_result_human_format() -> None:
    """Test output formatting for human-readable format."""
    result = PullResult(
        files_transferred=5,
        bytes_transferred=1024,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
    )
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)

    # Should not raise
    _output_result(result, output_opts)


def test_output_result_human_format_dry_run() -> None:
    """Test output formatting for human-readable format with dry run."""
    result = PullResult(
        files_transferred=5,
        bytes_transferred=0,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=True,
    )
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)

    # Should not raise
    _output_result(result, output_opts)


def test_output_result_json_format(capsys) -> None:
    """Test output formatting for JSON format."""
    result = PullResult(
        files_transferred=5,
        bytes_transferred=1024,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
    )
    output_opts = OutputOptions(output_format=OutputFormat.JSON)

    _output_result(result, output_opts)
    captured = capsys.readouterr()
    assert '"files_transferred": 5' in captured.out
    assert '"bytes_transferred": 1024' in captured.out


def test_output_result_jsonl_format(capsys) -> None:
    """Test output formatting for JSONL format."""
    result = PullResult(
        files_transferred=3,
        bytes_transferred=512,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
    )
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)

    _output_result(result, output_opts)
    captured = capsys.readouterr()
    assert "pull_complete" in captured.out


def test_find_agent_by_name_or_id_raises_for_empty_agents(temp_mngr_ctx: MngrContext) -> None:
    """Test that find_agent_by_name_or_id raises UserInputError for unknown agent."""
    agents_by_host: dict[HostReference, list[AgentReference]] = {}

    with pytest.raises(UserInputError, match="No agent found with name or ID"):
        find_and_maybe_start_agent_by_name_or_id("nonexistent-agent", agents_by_host, temp_mngr_ctx, "test")


def test_find_agent_by_name_or_id_raises_agent_not_found_for_valid_id(temp_mngr_ctx: MngrContext) -> None:
    """Test that find_agent_by_name_or_id raises AgentNotFoundError for valid but nonexistent ID."""
    agents_by_host: dict[HostReference, list[AgentReference]] = {}

    # Generate a valid agent ID that doesn't exist in the empty agents_by_host
    nonexistent_id = AgentId.generate()

    with pytest.raises(AgentNotFoundError):
        find_and_maybe_start_agent_by_name_or_id(str(nonexistent_id), agents_by_host, temp_mngr_ctx, "test")


def test_find_agent_by_name_or_id_raises_for_multiple_matches(
    temp_mngr_ctx: MngrContext,
    tmp_path: Path,
) -> None:
    """Test that find_agent_by_name_or_id raises for multiple agents with same name."""
    host1_id = HostId.generate()
    host2_id = HostId.generate()
    agent_name = AgentName("my-agent")

    host_ref1 = HostReference(
        host_id=host1_id,
        host_name=HostName("host1"),
        provider_name=ProviderInstanceName("local"),
    )
    host_ref2 = HostReference(
        host_id=host2_id,
        host_name=HostName("host2"),
        provider_name=ProviderInstanceName("local"),
    )

    agent_id1 = AgentId.generate()
    agent_id2 = AgentId.generate()

    agent_ref1 = AgentReference(
        host_id=host1_id,
        agent_id=agent_id1,
        agent_name=agent_name,
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref2 = AgentReference(
        host_id=host2_id,
        agent_id=agent_id2,
        agent_name=agent_name,
        provider_name=ProviderInstanceName("local"),
    )

    agents_by_host = {
        host_ref1: [agent_ref1],
        host_ref2: [agent_ref2],
    }

    # Create test agents
    test_agent1 = _create_test_agent(agent_id1, agent_name, host1_id, temp_mngr_ctx)
    test_agent2 = _create_test_agent(agent_id2, agent_name, host2_id, temp_mngr_ctx)

    # Create test hosts with real types (inheriting from Host)
    host_dir1 = tmp_path / "host1"
    host_dir1.mkdir()
    host_dir2 = tmp_path / "host2"
    host_dir2.mkdir()

    test_host1 = _create_test_host(host1_id, "test-host-1", [test_agent1], temp_mngr_ctx, host_dir1)
    test_host2 = _create_test_host(host2_id, "test-host-2", [test_agent2], temp_mngr_ctx, host_dir2)

    # Create a mock provider that returns our test hosts
    class MockProvider:
        name = ProviderInstanceName("local")

        def get_host(self, host_id: HostId) -> _TestHost:
            if host_id == host1_id:
                return test_host1
            else:
                return test_host2

    mock_provider = MockProvider()

    def mock_get_provider(provider_name: ProviderInstanceName, ctx: MngrContext) -> MockProvider:
        return mock_provider

    with patch("imbue.mngr.api.find.get_provider_instance", side_effect=mock_get_provider):
        with pytest.raises(UserInputError, match="Multiple agents found"):
            find_and_maybe_start_agent_by_name_or_id("my-agent", agents_by_host, temp_mngr_ctx, "test")
