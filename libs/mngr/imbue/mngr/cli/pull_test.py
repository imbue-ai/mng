"""Unit tests for pull CLI command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.api.sync import SyncMode
from imbue.mngr.api.test_fixtures import StubHost
from imbue.mngr.api.test_fixtures import create_test_agent
from imbue.mngr.api.test_fixtures import create_test_host
from imbue.mngr.cli.pull import PullCliOptions
from imbue.mngr.cli.pull import _output_files_result
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.main import cli
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import ProviderInstanceName


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
    assert "target_branch" in annotations


def test_pull_command_is_registered() -> None:
    """Test that pull command is registered in the CLI group."""
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--help"])
    assert result.exit_code == 0
    assert "Pull files or git commits from an agent" in result.output


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
    assert "git" in result.output
    assert "full" in result.output


def test_output_files_result_human_format() -> None:
    """Test output formatting for human-readable format."""
    result = SyncFilesResult(
        files_transferred=5,
        bytes_transferred=1024,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
        mode=SyncMode.PULL,
    )
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)

    _output_files_result(result, output_opts)


def test_output_files_result_human_format_dry_run() -> None:
    """Test output formatting for human-readable format with dry run."""
    result = SyncFilesResult(
        files_transferred=5,
        bytes_transferred=0,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=True,
        mode=SyncMode.PULL,
    )
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)

    _output_files_result(result, output_opts)


def test_output_files_result_json_format(capsys) -> None:
    """Test output formatting for JSON format."""
    result = SyncFilesResult(
        files_transferred=5,
        bytes_transferred=1024,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        is_dry_run=False,
        mode=SyncMode.PULL,
    )
    output_opts = OutputOptions(output_format=OutputFormat.JSON)

    _output_files_result(result, output_opts)
    captured = capsys.readouterr()
    assert '"files_transferred": 5' in captured.out
    assert '"bytes_transferred": 1024' in captured.out


def test_output_files_result_jsonl_format(capsys) -> None:
    """Test output formatting for JSONL format."""
    result = SyncFilesResult(
        files_transferred=3,
        bytes_transferred=512,
        source_path=Path("/src"),
        destination_path=Path("/dst"),
        mode=SyncMode.PULL,
        is_dry_run=False,
    )
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)

    _output_files_result(result, output_opts)
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
    test_agent1 = create_test_agent(agent_id1, agent_name, host1_id, temp_mngr_ctx)
    test_agent2 = create_test_agent(agent_id2, agent_name, host2_id, temp_mngr_ctx)

    # Create test hosts with real types (inheriting from Host)
    host_dir1 = tmp_path / "host1"
    host_dir1.mkdir()
    host_dir2 = tmp_path / "host2"
    host_dir2.mkdir()

    test_host1 = create_test_host(host1_id, "test-host-1", [test_agent1], temp_mngr_ctx, host_dir1)
    test_host2 = create_test_host(host2_id, "test-host-2", [test_agent2], temp_mngr_ctx, host_dir2)

    # Create a mock provider that returns our test hosts
    class MockProvider:
        name = ProviderInstanceName("local")

        def get_host(self, host_id: HostId) -> StubHost:
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
