"""Unit tests for pull CLI command."""

from pathlib import Path
from typing import cast

import pytest
from click.testing import CliRunner

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.sync import SyncFilesResult
from imbue.mngr.cli.output_helpers import output_sync_files_result
from imbue.mngr.cli.pull import PullCliOptions
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.main import cli
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SyncMode
from imbue.mngr.providers.local.instance import LocalProviderInstance


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

    output_sync_files_result(result, output_opts.output_format)


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

    output_sync_files_result(result, output_opts.output_format)


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

    output_sync_files_result(result, output_opts.output_format)
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

    output_sync_files_result(result, output_opts.output_format)
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
    local_provider: LocalProviderInstance,
    temp_mngr_ctx: MngrContext,
    tmp_path: Path,
) -> None:
    """Test that find_agent_by_name_or_id raises for multiple agents with same name."""
    local_host = cast(OnlineHostInterface, local_provider.get_host(HostName("local")))
    agent_name = AgentName("my-agent")

    # Create two agents with the same name on the local host
    work_dir1 = tmp_path / "work1"
    work_dir1.mkdir()
    work_dir2 = tmp_path / "work2"
    work_dir2.mkdir()

    agent1 = local_host.create_agent_state(
        work_dir_path=work_dir1,
        options=CreateAgentOptions(
            agent_type=AgentTypeName("generic"),
            name=agent_name,
            command=CommandString("sleep 58291"),
        ),
    )
    agent2 = local_host.create_agent_state(
        work_dir_path=work_dir2,
        options=CreateAgentOptions(
            agent_type=AgentTypeName("generic"),
            name=agent_name,
            command=CommandString("sleep 58292"),
        ),
    )

    # Build references matching the real host and agents
    host_ref = HostReference(
        host_id=local_host.id,
        host_name=local_host.get_name(),
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref1 = AgentReference(
        agent_id=agent1.id,
        agent_name=agent_name,
        host_id=local_host.id,
        provider_name=ProviderInstanceName("local"),
    )
    agent_ref2 = AgentReference(
        agent_id=agent2.id,
        agent_name=agent_name,
        host_id=local_host.id,
        provider_name=ProviderInstanceName("local"),
    )

    agents_by_host = {host_ref: [agent_ref1, agent_ref2]}

    with pytest.raises(UserInputError, match="Multiple agents found"):
        find_and_maybe_start_agent_by_name_or_id("my-agent", agents_by_host, temp_mngr_ctx, "test")
