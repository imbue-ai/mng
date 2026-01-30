"""Additional unit tests for pull CLI command to improve coverage.

These tests cover:
- _select_agent_for_pull function
- Source specification parsing (AGENT, AGENT:PATH, PATH formats)
- Path resolution (absolute vs relative paths)
- Remote agent host check
- Conditional agent stop
"""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from imbue.mngr.api.list import AgentInfo
from imbue.mngr.api.list import ListResult
from imbue.mngr.api.pull import PullResult
from imbue.mngr.cli.pull import PullCliOptions
from imbue.mngr.cli.pull import _select_agent_for_pull
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.agent import AgentStatus
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.main import cli
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import OutputFormat
from imbue.mngr.primitives import ProviderInstanceName


def _make_agent_info(
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


def test_select_agent_for_pull_raises_when_no_agents_available() -> None:
    """Test that _select_agent_for_pull raises UserInputError when no agents exist."""
    mock_ctx = MagicMock()

    with patch("imbue.mngr.cli.pull.list_agents") as mock_list:
        mock_list.return_value = ListResult(agents=[], errors=[])

        with pytest.raises(UserInputError, match="No agents found"):
            _select_agent_for_pull(mock_ctx)


def test_select_agent_for_pull_returns_none_when_user_cancels() -> None:
    """Test that _select_agent_for_pull returns None when user cancels selection."""
    mock_ctx = MagicMock()

    agent_info = _make_agent_info()

    with (
        patch("imbue.mngr.cli.pull.list_agents") as mock_list,
        patch("imbue.mngr.cli.pull.select_agent_interactively") as mock_select,
    ):
        mock_list.return_value = ListResult(agents=[agent_info], errors=[])
        mock_select.return_value = None

        result = _select_agent_for_pull(mock_ctx)
        assert result is None


def test_select_agent_for_pull_returns_agent_and_host_on_selection() -> None:
    """Test that _select_agent_for_pull returns (agent, host) tuple when user selects."""
    mock_ctx = MagicMock()

    agent_id = AgentId.generate()
    agent_info = _make_agent_info(agent_id=agent_id)

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
        mock_find.assert_called_once_with(str(agent_id), {}, mock_ctx, "pull")


def _create_mock_opts(
    source: str = "my-agent",
    source_agent: str | None = None,
    source_host: str | None = None,
    source_path: str | None = None,
    destination: str | None = None,
    dry_run: bool = False,
    stop: bool = False,
    delete: bool = False,
    sync_mode: str = "files",
) -> MagicMock:
    """Helper to create mock PullCliOptions."""
    mock_opts = MagicMock(spec=PullCliOptions)
    mock_opts.source = source
    mock_opts.source_agent = source_agent
    mock_opts.source_host = source_host
    mock_opts.source_path = source_path
    mock_opts.destination = destination
    mock_opts.dry_run = dry_run
    mock_opts.stop = stop
    mock_opts.delete = delete
    mock_opts.sync_mode = sync_mode
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


class TestSourceSpecificationParsing:
    """Tests for source specification parsing (AGENT, AGENT:PATH, PATH formats)."""

    def test_parse_agent_only_format(self) -> None:
        """Test that source='my-agent' is parsed as agent identifier."""
        runner = CliRunner()

        mock_agent = MagicMock()
        mock_agent.name = AgentName("my-agent")
        mock_agent.work_dir = Path("/work/dir")

        mock_host = MagicMock()
        mock_host.is_local = True
        mock_host.execute_command.return_value = MagicMock(
            success=True,
            stdout="sending incremental file list\nsent 100 bytes  received 50 bytes\n",
            stderr="",
        )

        with (
            patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup,
            patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
            patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
            patch("imbue.mngr.cli.pull.pull_files") as mock_pull,
            patch("imbue.mngr.cli.pull._output_result"),
        ):
            mock_opts = _create_mock_opts(source="my-agent")
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

            mock_find.assert_called_once()
            call_args = mock_find.call_args[0]
            assert call_args[0] == "my-agent"

    def test_parse_agent_colon_path_format(self) -> None:
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
            mock_opts = _create_mock_opts(source="my-agent:src/code")
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

            mock_pull.assert_called_once()
            pull_kwargs = mock_pull.call_args[1]
            assert pull_kwargs["source_path"] == Path("/work/dir/src/code")

    def test_path_only_format_raises_error(self) -> None:
        """Test that source starting with '/' without agent raises UserInputError."""
        runner = CliRunner()

        with patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup:
            mock_opts = _create_mock_opts(source="/absolute/path")
            mock_setup.return_value = (
                MagicMock(),
                OutputOptions(output_format=OutputFormat.HUMAN),
                mock_opts,
            )

            result = runner.invoke(cli, ["pull", "/absolute/path"])

            assert result.exit_code != 0
            assert "Source must include an agent specification" in result.output


class TestPathResolution:
    """Tests for path resolution (absolute vs relative paths)."""

    def test_absolute_source_path_used_as_is(self) -> None:
        """Test that absolute source_path is used directly without modification."""
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
            mock_opts = _create_mock_opts(
                source="my-agent",
                source_path="/absolute/custom/path",
            )
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
                source_path=Path("/absolute/custom/path"),
                destination_path=Path.cwd(),
                is_dry_run=False,
            )

            runner.invoke(cli, ["pull", "my-agent", "--source-path", "/absolute/custom/path"])

            mock_pull.assert_called_once()
            pull_kwargs = mock_pull.call_args[1]
            assert pull_kwargs["source_path"] == Path("/absolute/custom/path")

    def test_relative_source_path_resolved_to_work_dir(self) -> None:
        """Test that relative source_path is resolved relative to agent's work_dir."""
        runner = CliRunner()

        mock_agent = MagicMock()
        mock_agent.name = AgentName("my-agent")
        mock_agent.work_dir = Path("/agent/work/dir")

        mock_host = MagicMock()
        mock_host.is_local = True

        with (
            patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup,
            patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
            patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
            patch("imbue.mngr.cli.pull.pull_files") as mock_pull,
            patch("imbue.mngr.cli.pull._output_result"),
        ):
            mock_opts = _create_mock_opts(
                source="my-agent",
                source_path="relative/subdir",
            )
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
                source_path=Path("/agent/work/dir/relative/subdir"),
                destination_path=Path.cwd(),
                is_dry_run=False,
            )

            runner.invoke(cli, ["pull", "my-agent", "--source-path", "relative/subdir"])

            mock_pull.assert_called_once()
            pull_kwargs = mock_pull.call_args[1]
            assert pull_kwargs["source_path"] == Path("/agent/work/dir/relative/subdir")


def test_remote_agent_host_raises_not_implemented() -> None:
    """Test that pulling from remote agents raises NotImplementedError."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_agent.name = AgentName("my-agent")
    mock_agent.work_dir = Path("/work/dir")

    mock_host = MagicMock()
    mock_host.is_local = False

    with (
        patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup,
        patch("imbue.mngr.cli.pull.load_all_agents_grouped_by_host") as mock_load,
        patch("imbue.mngr.cli.pull.find_and_maybe_start_agent_by_name_or_id") as mock_find,
    ):
        mock_opts = _create_mock_opts(source="remote-agent")
        mock_setup.return_value = (
            MagicMock(),
            OutputOptions(output_format=OutputFormat.HUMAN),
            mock_opts,
        )
        mock_load.return_value = {}
        mock_find.return_value = (mock_agent, mock_host)

        result = runner.invoke(cli, ["pull", "remote-agent"])

        assert result.exit_code != 0
        assert "Pulling from remote agents is not implemented yet" in result.output or (
            result.exception is not None
            and "Pulling from remote agents is not implemented yet" in str(result.exception)
        )


def test_conditional_agent_stop_when_stop_is_true() -> None:
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
        mock_opts = _create_mock_opts(source="my-agent", stop=True)
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


def test_conditional_agent_stop_not_called_when_stop_is_false() -> None:
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
        mock_opts = _create_mock_opts(source="my-agent", stop=False)
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


def test_source_and_source_agent_conflict_raises_error() -> None:
    """Test that conflicting --source and --source-agent values raise UserInputError."""
    runner = CliRunner()

    with patch("imbue.mngr.cli.pull.setup_command_context") as mock_setup:
        mock_opts = _create_mock_opts(source="agent-one", source_agent="agent-two")
        mock_setup.return_value = (
            MagicMock(),
            OutputOptions(output_format=OutputFormat.HUMAN),
            mock_opts,
        )

        result = runner.invoke(cli, ["pull", "agent-one", "--source-agent", "agent-two"])

        assert result.exit_code != 0
        assert "Cannot specify both --source and --source-agent with different values" in result.output
