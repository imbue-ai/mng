"""Unit tests for pull CLI command."""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.list import AgentInfo
from imbue.mngr.api.list import ListResult
from imbue.mngr.api.pull import PullResult
from imbue.mngr.cli.pull import PullCliOptions
from imbue.mngr.cli.pull import _output_result
from imbue.mngr.cli.pull import _select_agent_for_pull
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentStatus
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.main import cli
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import CommandString
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
        find_and_maybe_start_agent_by_name_or_id("nonexistent-agent", agents_by_host, mock_ctx, "test")


def test_find_agent_by_name_or_id_raises_agent_not_found_for_valid_id() -> None:
    """Test that find_agent_by_name_or_id raises AgentNotFoundError for valid but nonexistent ID."""
    mock_ctx = MagicMock()
    agents_by_host: dict[HostReference, list[AgentReference]] = {}

    # Generate a valid agent ID that doesn't exist in the empty agents_by_host
    nonexistent_id = AgentId.generate()

    with pytest.raises(AgentNotFoundError):
        find_and_maybe_start_agent_by_name_or_id(str(nonexistent_id), agents_by_host, mock_ctx, "test")


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
            find_and_maybe_start_agent_by_name_or_id("my-agent", agents_by_host, mock_ctx, "test")


# =============================================================================
# Tests for _select_agent_for_pull
# =============================================================================


def _make_agent_info_for_pull(
    agent_id: AgentId | None = None,
    agent_name: str = "test-agent",
) -> AgentInfo:
    """Helper to create an AgentInfo object for testing."""
    if agent_id is None:
        agent_id = AgentId.generate()

    host_id = HostId.generate()
    return AgentInfo(
        id=agent_id,
        name=AgentName(agent_name),
        type="claude",
        command=CommandString("claude"),
        work_dir=Path("/work/dir"),
        create_time=datetime.now(timezone.utc),
        start_on_boot=False,
        lifecycle_state=AgentLifecycleState.RUNNING,
        status=AgentStatus(line="Running", full="Agent is running"),
        url=None,
        start_time=None,
        runtime_seconds=None,
        user_activity_time=None,
        agent_activity_time=None,
        ssh_activity_time=None,
        idle_seconds=None,
        idle_mode=None,
        host=HostInfo(
            id=host_id,
            name=HostName("test-host"),
            provider_name=ProviderInstanceName("local"),
            host="localhost",
            state="running",
            image=None,
            tags={},
            boot_time=None,
            uptime_seconds=None,
            resource=None,
            ssh=None,
            snapshots=[],
        ),
    )


def test_select_agent_for_pull_raises_when_no_agents() -> None:
    """Test that _select_agent_for_pull raises UserInputError when no agents exist."""
    mock_ctx = MagicMock()

    with patch("imbue.mngr.cli.pull.list_agents") as mock_list:
        mock_list.return_value = ListResult(agents=[], errors=[])

        with pytest.raises(UserInputError, match="No agents found"):
            _select_agent_for_pull(mock_ctx)


def test_select_agent_for_pull_returns_none_when_cancelled() -> None:
    """Test that _select_agent_for_pull returns None when user cancels selection."""
    mock_ctx = MagicMock()
    agent_info = _make_agent_info_for_pull()

    with (
        patch("imbue.mngr.cli.pull.list_agents") as mock_list,
        patch("imbue.mngr.cli.pull.select_agent_interactively") as mock_select,
    ):
        mock_list.return_value = ListResult(agents=[agent_info], errors=[])
        mock_select.return_value = None

        result = _select_agent_for_pull(mock_ctx)
        assert result is None


def test_select_agent_for_pull_returns_agent_host_tuple() -> None:
    """Test that _select_agent_for_pull returns (agent, host) tuple when user selects."""
    mock_ctx = MagicMock()
    agent_id = AgentId.generate()
    agent_info = _make_agent_info_for_pull(agent_id=agent_id)

    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_host = MagicMock()

    with (
        patch("imbue.mngr.cli.pull.list_agents") as mock_list,
        patch("imbue.mngr.cli.pull.select_agent_interactively") as mock_select,
        patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
        patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
    ):
        mock_list.return_value = ListResult(agents=[agent_info], errors=[])
        mock_select.return_value = agent_info
        mock_load.return_value = {}
        mock_find.return_value = (mock_agent, mock_host)

        result = _select_agent_for_pull(mock_ctx)

        assert result is not None
        assert result[0] == mock_agent
        assert result[1] == mock_host


# =============================================================================
# Tests for source specification parsing
# =============================================================================


def _create_mock_pull_opts(
    source: str = "my-agent",
    source_agent: str | None = None,
    source_path: str | None = None,
    stop: bool = False,
) -> MagicMock:
    """Helper to create mock PullCliOptions."""
    mock_opts = MagicMock(spec=PullCliOptions)
    mock_opts.source = source
    mock_opts.source_agent = source_agent
    mock_opts.source_host = None
    mock_opts.source_path = source_path
    mock_opts.destination = None
    mock_opts.dry_run = False
    mock_opts.stop = stop
    mock_opts.delete = False
    mock_opts.sync_mode = "files"
    mock_opts.exclude = ()
    mock_opts.target = None
    mock_opts.target_agent = None
    mock_opts.target_host = None
    mock_opts.target_path = None
    mock_opts.stdin = False
    mock_opts.include = ()
    mock_opts.include_gitignored = False
    mock_opts.include_file = None
    mock_opts.exclude_file = None
    mock_opts.rsync_arg = ()
    mock_opts.rsync_args = None
    mock_opts.branch = ()
    mock_opts.target_branch = None
    mock_opts.all_branches = False
    mock_opts.tags = False
    mock_opts.force_git = False
    mock_opts.merge = False
    mock_opts.rebase = False
    mock_opts.uncommitted_source = None
    return mock_opts


def test_pull_source_agent_colon_path_format() -> None:
    """Test that source='agent:path/to/file' is parsed correctly."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.name = AgentName("my-agent")
    mock_agent.work_dir = Path("/work/dir")

    mock_host = MagicMock()
    mock_host.is_local = True

    with (
        patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup,
        patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
        patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
        patch("imbue.mngr.cli.pull.pull_files") as mock_pull,
        patch("imbue.mngr.cli.pull._output_result"),
    ):
        mock_opts = _create_mock_pull_opts(source="my-agent:src/code")
        mock_setup.return_value = (
            MagicMock(),
            OutputOptions(output_format=OutputFormat.HUMAN),
            mock_opts,
        )
        mock_load.return_value = {}
        mock_find.return_value = (mock_agent, mock_host)
        mock_pull.return_value = PullResult(
            files_transferred=0,
            bytes_transferred=0,
            source_path=Path("/work/dir/src/code"),
            destination_path=Path.cwd(),
            is_dry_run=False,
        )

        runner.invoke(cli, ["pull", "my-agent:src/code"])

        mock_find.assert_called_once()
        call_args = mock_find.call_args[0]
        assert call_args[0] == "my-agent"


def test_pull_conditional_stop_when_true() -> None:
    """Test that host.stop_agents is called when opts.stop is True."""
    runner = CliRunner()

    agent_id = AgentId.generate()
    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_agent.name = AgentName("my-agent")
    mock_agent.work_dir = Path("/work/dir")

    mock_host = MagicMock()
    mock_host.is_local = True

    with (
        patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup,
        patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
        patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
        patch("imbue.mngr.cli.pull.pull_files") as mock_pull,
        patch("imbue.mngr.cli.pull._output_result"),
    ):
        mock_opts = _create_mock_pull_opts(source="my-agent", stop=True)
        mock_setup.return_value = (
            MagicMock(),
            OutputOptions(output_format=OutputFormat.HUMAN),
            mock_opts,
        )
        mock_load.return_value = {}
        mock_find.return_value = (mock_agent, mock_host)
        mock_pull.return_value = PullResult(
            files_transferred=0,
            bytes_transferred=0,
            source_path=Path("/work/dir"),
            destination_path=Path.cwd(),
            is_dry_run=False,
        )

        runner.invoke(cli, ["pull", "my-agent", "--stop"])

        mock_host.stop_agents.assert_called_once_with([agent_id])


def test_pull_conditional_stop_not_called_when_false() -> None:
    """Test that host.stop_agents is NOT called when opts.stop is False."""
    runner = CliRunner()

    agent_id = AgentId.generate()
    mock_agent = MagicMock()
    mock_agent.id = agent_id
    mock_agent.name = AgentName("my-agent")
    mock_agent.work_dir = Path("/work/dir")

    mock_host = MagicMock()
    mock_host.is_local = True

    with (
        patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup,
        patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
        patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
        patch("imbue.mngr.cli.pull.pull_files") as mock_pull,
        patch("imbue.mngr.cli.pull._output_result"),
    ):
        mock_opts = _create_mock_pull_opts(source="my-agent", stop=False)
        mock_setup.return_value = (
            MagicMock(),
            OutputOptions(output_format=OutputFormat.HUMAN),
            mock_opts,
        )
        mock_load.return_value = {}
        mock_find.return_value = (mock_agent, mock_host)
        mock_pull.return_value = PullResult(
            files_transferred=0,
            bytes_transferred=0,
            source_path=Path("/work/dir"),
            destination_path=Path.cwd(),
            is_dry_run=False,
        )

        runner.invoke(cli, ["pull", "my-agent"])

        mock_host.stop_agents.assert_not_called()
