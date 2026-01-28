"""Unit tests for pull CLI command."""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from imbue.mngr.api.pull import PullResult
from imbue.mngr.cli.pull import PullCliOptions
from imbue.mngr.api.find import find_agent_by_name_or_id
from imbue.mngr.cli.pull import _output_result
from imbue.mngr.config.data_types import OutputOptions
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


def test_find_agent_by_name_or_id_raises_for_empty_agents() -> None:
    """Test that find_agent_by_name_or_id raises UserInputError for unknown agent."""
    mock_ctx = MagicMock()
    agents_by_host: dict[HostReference, list[AgentReference]] = {}

    with pytest.raises(UserInputError, match="No agent found with name or ID"):
        find_agent_by_name_or_id("nonexistent-agent", agents_by_host, mock_ctx, "test")


def test_find_agent_by_name_or_id_raises_for_multiple_matches() -> None:
    """Test that find_agent_by_name_or_id raises for multiple agents with same name."""
    mock_ctx = MagicMock()

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

    agent_ref1 = AgentReference(
        host_id=host1_id,
        agent_id=AgentId.generate(),
        agent_name=agent_name,
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref2 = AgentReference(
        host_id=host2_id,
        agent_id=AgentId.generate(),
        agent_name=agent_name,
        provider_name=ProviderInstanceName("local"),
    )

    agents_by_host = {
        host_ref1: [agent_ref1],
        host_ref2: [agent_ref2],
    }

    # Mock get_provider_instance to return mock providers with correct agent IDs
    def mock_get_provider(provider_name, ctx):
        mock_provider = MagicMock()

        # Return different agents based on which host is requested
        def mock_get_host(host_id):
            mock_host_instance = MagicMock()
            if host_id == host1_id:
                mock_agent1 = MagicMock()
                mock_agent1.id = agent_ref1.agent_id
                mock_agent1.name = agent_name
                mock_host_instance.get_agents.return_value = [mock_agent1]
            else:
                mock_agent2 = MagicMock()
                mock_agent2.id = agent_ref2.agent_id
                mock_agent2.name = agent_name
                mock_host_instance.get_agents.return_value = [mock_agent2]
            mock_host_instance.connector.name = "mock-host"
            return mock_host_instance

        mock_provider.get_host.side_effect = mock_get_host
        return mock_provider

    with patch("imbue.mngr.api.find.get_provider_instance", side_effect=mock_get_provider):
        with pytest.raises(UserInputError, match="Multiple agents found"):
            find_agent_by_name_or_id("my-agent", agents_by_host, mock_ctx, "test")


def test_find_agent_by_name_or_id_finds_agent_by_valid_id() -> None:
    """Test that find_agent_by_name_or_id can find an agent by its ID."""
    mock_ctx = MagicMock()

    host_id = HostId.generate()
    agent_id = AgentId.generate()
    agent_name = AgentName("my-agent")

    host_ref = HostReference(
        host_id=host_id,
        host_name=HostName("host1"),
        provider_name=ProviderInstanceName("local"),
    )

    agent_ref = AgentReference(
        host_id=host_id,
        agent_id=agent_id,
        agent_name=agent_name,
        provider_name=ProviderInstanceName("local"),
    )

    agents_by_host = {
        host_ref: [agent_ref],
    }

    # Mock get_provider_instance to return mock providers
    mock_provider = MagicMock()
    mock_host = MagicMock()
    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_agent.name = agent_name
    mock_host.get_agents.return_value = [mock_agent]
    mock_provider.get_host.return_value = mock_host

    with patch("imbue.mngr.api.find.get_provider_instance", return_value=mock_provider):
        found_agent, found_host = find_agent_by_name_or_id(str(agent_id), agents_by_host, mock_ctx, "test")
        assert found_agent.id == agent_id


def test_find_agent_by_name_or_id_finds_agent_by_name() -> None:
    """Test that find_agent_by_name_or_id can find an agent by its name."""
    mock_ctx = MagicMock()

    host_id = HostId.generate()
    agent_id = AgentId.generate()
    agent_name = AgentName("my-agent")

    host_ref = HostReference(
        host_id=host_id,
        host_name=HostName("host1"),
        provider_name=ProviderInstanceName("local"),
    )

    agent_ref = AgentReference(
        host_id=host_id,
        agent_id=agent_id,
        agent_name=agent_name,
        provider_name=ProviderInstanceName("local"),
    )

    agents_by_host = {
        host_ref: [agent_ref],
    }

    # Mock get_provider_instance to return mock providers
    mock_provider = MagicMock()
    mock_host = MagicMock()
    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_agent.name = agent_name
    mock_host.get_agents.return_value = [mock_agent]
    mock_provider.get_host.return_value = mock_host

    with patch("imbue.mngr.api.find.get_provider_instance", return_value=mock_provider):
        found_agent, found_host = find_agent_by_name_or_id("my-agent", agents_by_host, mock_ctx, "test")
        assert found_agent.name == agent_name
