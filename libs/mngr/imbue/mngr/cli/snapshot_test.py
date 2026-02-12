"""Unit tests for the snapshot CLI command."""

from datetime import datetime
from datetime import timezone
from unittest.mock import MagicMock
from unittest.mock import patch

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.snapshot import SnapshotCreateCliOptions
from imbue.mngr.cli.snapshot import SnapshotDestroyCliOptions
from imbue.mngr.cli.snapshot import SnapshotListCliOptions
from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName

# Valid HostId for use in mocked test data (host- prefix + 32 hex characters)
VALID_HOST_ID = "host-" + "a" * 32


# =============================================================================
# Options classes tests
# =============================================================================


def test_snapshot_create_cli_options_fields() -> None:
    """Test SnapshotCreateCliOptions has required fields."""
    opts = SnapshotCreateCliOptions(
        agents=("agent1",),
        agent_list=("agent2",),
        hosts=("host1",),
        all_agents=False,
        name="my-snapshot",
        dry_run=True,
        include=(),
        exclude=(),
        stdin=False,
        tag=(),
        description=None,
        restart_if_larger_than=None,
        pause_during=True,
        wait=True,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agents == ("agent1",)
    assert opts.agent_list == ("agent2",)
    assert opts.hosts == ("host1",)
    assert opts.all_agents is False
    assert opts.name == "my-snapshot"
    assert opts.dry_run is True


def test_snapshot_list_cli_options_fields() -> None:
    """Test SnapshotListCliOptions has required fields."""
    opts = SnapshotListCliOptions(
        agents=("agent1",),
        agent_list=(),
        all_agents=False,
        limit=10,
        include=(),
        exclude=(),
        after=None,
        before=None,
        output_format="json",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.agents == ("agent1",)
    assert opts.limit == 10


def test_snapshot_destroy_cli_options_fields() -> None:
    """Test SnapshotDestroyCliOptions has required fields."""
    opts = SnapshotDestroyCliOptions(
        agents=("agent1",),
        agent_list=(),
        snapshots=("snap-123",),
        all_snapshots=False,
        force=True,
        dry_run=False,
        include=(),
        exclude=(),
        stdin=False,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.snapshots == ("snap-123",)
    assert opts.force is True


# =============================================================================
# Group help tests
# =============================================================================


def test_snapshot_group_shows_help_without_subcommand(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot group exits successfully when invoked without subcommand."""
    result = cli_runner.invoke(
        snapshot,
        [],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    # Group shows help via logger.info (goes to stderr before logging is configured)
    assert result.exit_code == 0


def test_snapshot_group_help_flag(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that snapshot --help works."""
    result = cli_runner.invoke(
        snapshot,
        ["--help"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


# =============================================================================
# create subcommand tests
# =============================================================================


def test_snapshot_create_requires_target(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that create requires at least one agent, host, or --all."""
    result = cli_runner.invoke(
        snapshot,
        ["create"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Must specify at least one agent, host, or use --all" in result.output


def test_snapshot_create_cannot_combine_agents_and_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --all cannot be combined with agent names."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--all"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Cannot specify both agent names and --all" in result.output


def test_snapshot_create_nonexistent_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test creating a snapshot for a non-existent agent."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "nonexistent-agent-99999"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_all_with_no_running_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test creating snapshots for all agents when none are running."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "--all"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


def test_snapshot_create_dry_run(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --dry-run with --all shows what would be done."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "--all", "--dry-run"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_create_success(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test successful snapshot creation."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.create_snapshot.return_value = SnapshotId("snap-abc")
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    mock_provider.create_snapshot.assert_called_once()


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_create_unsupported_provider(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test creating a snapshot with a provider that doesn't support snapshots."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("local"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = False
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "does not support snapshots" in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_create_json_output(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot create with JSON output format."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.create_snapshot.return_value = SnapshotId("snap-json")
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-json" in result.output
    assert "snapshots_created" in result.output


# =============================================================================
# list subcommand tests
# =============================================================================


def test_snapshot_list_requires_target(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list requires at least one agent or --all."""
    result = cli_runner.invoke(
        snapshot,
        ["list"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Must specify at least one agent or use --all" in result.output


def test_snapshot_list_cannot_combine_agents_and_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that list --all cannot be combined with agent names."""
    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--all"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Cannot specify both agent names and --all" in result.output


def test_snapshot_list_all_with_no_running_agents(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test listing snapshots for all agents when none are running."""
    result = cli_runner.invoke(
        snapshot,
        ["list", "--all"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_list_success(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test successful snapshot listing with JSON output."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId("snap-001"),
            name=SnapshotName("before-refactor"),
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            size_bytes=256 * 1024 * 1024,
        ),
        SnapshotInfo(
            id=SnapshotId("snap-002"),
            name=SnapshotName("auto-stop"),
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            size_bytes=64 * 1024 * 1024,
        ),
    ]
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-001" in result.output
    assert "before-refactor" in result.output
    assert "snap-002" in result.output
    assert "auto-stop" in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_list_with_limit(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot list with --limit."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId("snap-001"),
            name=SnapshotName("first"),
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        ),
        SnapshotInfo(
            id=SnapshotId("snap-002"),
            name=SnapshotName("second"),
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--limit", "1", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-001" in result.output
    assert "snap-002" not in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_list_json_output(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot list with JSON output."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId("snap-json-1"),
            name=SnapshotName("test"),
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
            size_bytes=1024,
        ),
    ]
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-json-1" in result.output
    assert "snapshots" in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_list_jsonl_output(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test snapshot list with JSONL output."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId("snap-jsonl-1"),
            name=SnapshotName("test"),
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        ),
    ]
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snap-jsonl-1" in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_list_no_snapshots(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test listing when there are no snapshots (JSON output)."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = []
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert '"count": 0' in result.output


# =============================================================================
# destroy subcommand tests
# =============================================================================


def test_snapshot_destroy_requires_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that destroy requires at least one agent."""
    result = cli_runner.invoke(
        snapshot,
        ["destroy", "--all-snapshots", "--force"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Must specify at least one agent" in result.output


def test_snapshot_destroy_requires_snapshot_or_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that destroy requires --snapshot or --all-snapshots."""
    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Must specify --snapshot or --all-snapshots" in result.output


def test_snapshot_destroy_cannot_combine_snapshot_and_all(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --snapshot and --all-snapshots cannot be combined."""
    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--snapshot", "snap-123", "--all-snapshots", "--force"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    assert "Cannot specify both --snapshot and --all-snapshots" in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_destroy_with_force(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying a specific snapshot with --force."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--snapshot", "snap-123", "--force"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    mock_provider.delete_snapshot.assert_called_once()


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_destroy_all_snapshots_with_force(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroying all snapshots with --force."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId("snap-001"),
            name=SnapshotName("first"),
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        ),
        SnapshotInfo(
            id=SnapshotId("snap-002"),
            name=SnapshotName("second"),
            created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        ),
    ]
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--force"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert mock_provider.delete_snapshot.call_count == 2


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_destroy_dry_run(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroy --dry-run does not actually delete (JSONL output for stdout)."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = [
        SnapshotInfo(
            id=SnapshotId("snap-001"),
            name=SnapshotName("first"),
            created_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc),
        ),
    ]
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--dry-run", "--format", "jsonl"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "Would destroy" in result.output
    mock_provider.delete_snapshot.assert_not_called()


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_destroy_json_output(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroy with JSON output."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--snapshot", "snap-123", "--force", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "snapshots_destroyed" in result.output


@patch("imbue.mngr.cli.snapshot.get_provider_instance")
@patch("imbue.mngr.cli.snapshot._resolve_snapshot_hosts")
def test_snapshot_destroy_no_snapshots_found(
    mock_resolve: MagicMock,
    mock_get_provider: MagicMock,
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test destroy --all-snapshots when no snapshots exist (JSON output)."""
    mock_resolve.return_value = [
        (VALID_HOST_ID, ProviderInstanceName("modal"), ["my-agent"]),
    ]
    mock_provider = MagicMock()
    mock_provider.supports_snapshots = True
    mock_provider.list_snapshots.return_value = []
    mock_get_provider.return_value = mock_provider

    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--force", "--format", "json"],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert '"count": 0' in result.output


# =============================================================================
# Future option tests
# =============================================================================


def test_snapshot_create_include_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --include raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--include", "some-filter"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_exclude_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --exclude raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--exclude", "some-filter"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_stdin_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --stdin raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--stdin"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_tag_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --tag raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--tag", "key=value"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_description_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --description raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--description", "some desc"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_create_no_wait_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --no-wait raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["create", "my-agent", "--no-wait"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_list_after_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --after raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["list", "my-agent", "--after", "2024-01-01"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0


def test_snapshot_destroy_stdin_raises_not_implemented(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that --stdin on destroy raises NotImplementedError."""
    result = cli_runner.invoke(
        snapshot,
        ["destroy", "my-agent", "--all-snapshots", "--stdin"],
        obj=plugin_manager,
        catch_exceptions=True,
    )
    assert result.exit_code != 0
