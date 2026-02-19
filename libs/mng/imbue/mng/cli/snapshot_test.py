import pluggy
from click.testing import CliRunner

from imbue.mng.cli.snapshot import SnapshotCreateCliOptions
from imbue.mng.cli.snapshot import SnapshotDestroyCliOptions
from imbue.mng.cli.snapshot import SnapshotListCliOptions
from imbue.mng.cli.snapshot import _classify_mixed_identifiers
from imbue.mng.cli.snapshot import snapshot
from imbue.mng.config.data_types import MngContext
from imbue.mng.main import cli

# =============================================================================
# Options classes tests
# =============================================================================


def test_snapshot_create_cli_options_fields() -> None:
    """Test SnapshotCreateCliOptions has required fields."""
    opts = SnapshotCreateCliOptions(
        identifiers=("agent1",),
        agent_list=("agent2",),
        hosts=("host1",),
        all_agents=False,
        name="my-snapshot",
        dry_run=True,
        on_error="continue",
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
    assert opts.identifiers == ("agent1",)
    assert opts.agent_list == ("agent2",)
    assert opts.hosts == ("host1",)
    assert opts.all_agents is False
    assert opts.name == "my-snapshot"
    assert opts.dry_run is True
    assert opts.on_error == "continue"


def test_snapshot_list_cli_options_fields() -> None:
    """Test SnapshotListCliOptions has required fields."""
    opts = SnapshotListCliOptions(
        identifiers=("agent1",),
        agent_list=(),
        hosts=("host1",),
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
    assert opts.identifiers == ("agent1",)
    assert opts.hosts == ("host1",)
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
# _SnapshotGroup default-to-create tests
# =============================================================================


def test_snapshot_bare_invocation_defaults_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mng snapshot` with no args should forward to `snapshot create`."""
    result = cli_runner.invoke(snapshot, [], obj=plugin_manager)
    # Should attempt to run create (which errors asking for an agent),
    # not show group help or say "Missing command".
    assert "Missing command" not in result.output
    assert "Commands:" not in result.output
    assert "Must specify at least one agent" in result.output


def test_snapshot_unrecognized_subcommand_forwards_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mng snapshot nonexistent` should forward to `snapshot create nonexistent`.

    The local provider only accepts "localhost" as a host name, so
    "nonexistent" fails with "not found". The key assertion is that it
    does NOT say "No such command".
    """
    result = cli_runner.invoke(snapshot, ["nonexistent"], obj=plugin_manager)
    assert "No such command" not in result.output
    assert "Agent or host not found: nonexistent" in result.output


def test_snapshot_explicit_create_still_works(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mng snapshot create --help` should still work.

    Must invoke through the root cli group so that _build_help_key produces
    the correct qualified key ("snapshot.create") for metadata resolution.
    """
    result = cli_runner.invoke(cli, ["snapshot", "create", "--help"])
    assert result.exit_code == 0
    assert "Create a snapshot" in result.output


def test_snapshot_list_subcommand_not_forwarded(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mng snapshot list` should NOT be forwarded to create.

    Must invoke through the root cli group for correct help key resolution.
    """
    result = cli_runner.invoke(cli, ["snapshot", "list", "--help"])
    assert result.exit_code == 0
    assert "List snapshots" in result.output


def test_snapshot_destroy_subcommand_not_forwarded(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mng snapshot destroy` should NOT be forwarded to create.

    Must invoke through the root cli group for correct help key resolution.
    """
    result = cli_runner.invoke(cli, ["snapshot", "destroy", "--help"])
    assert result.exit_code == 0
    assert "Destroy snapshots" in result.output


# =============================================================================
# _classify_mixed_identifiers tests
# =============================================================================


def test_classify_mixed_identifiers_empty_input_returns_empty_lists(
    temp_mng_ctx: MngContext,
) -> None:
    """Empty identifier list returns two empty lists."""
    agent_ids, host_ids = _classify_mixed_identifiers([], temp_mng_ctx)
    assert agent_ids == []
    assert host_ids == []


def test_classify_mixed_identifiers_no_agents_treats_all_as_hosts(
    temp_mng_ctx: MngContext,
) -> None:
    """When no agents exist, all identifiers are classified as host identifiers."""
    agent_ids, host_ids = _classify_mixed_identifiers(["foo", "bar"], temp_mng_ctx)
    assert agent_ids == []
    assert host_ids == ["foo", "bar"]
