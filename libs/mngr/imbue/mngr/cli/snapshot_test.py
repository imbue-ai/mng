import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.snapshot import SnapshotCreateCliOptions
from imbue.mngr.cli.snapshot import SnapshotDestroyCliOptions
from imbue.mngr.cli.snapshot import SnapshotListCliOptions
from imbue.mngr.cli.snapshot import _classify_mixed_identifiers
from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.config.data_types import MngrContext

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
# _SnapshotGroup default-to-create tests
# =============================================================================


def test_snapshot_bare_invocation_defaults_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr snapshot` with no args should forward to `snapshot create`."""
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
    """Running `mngr snapshot nonexistent` should forward to `snapshot create nonexistent`.

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
    """Running `mngr snapshot create --help` should still work."""
    result = cli_runner.invoke(snapshot, ["create", "--help"], obj=plugin_manager)
    assert result.exit_code == 0
    assert "Create a snapshot" in result.output


def test_snapshot_list_subcommand_not_forwarded(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr snapshot list` should NOT be forwarded to create."""
    result = cli_runner.invoke(snapshot, ["list", "--help"], obj=plugin_manager)
    assert result.exit_code == 0
    assert "List snapshots" in result.output


def test_snapshot_destroy_subcommand_not_forwarded(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr snapshot destroy` should NOT be forwarded to create."""
    result = cli_runner.invoke(snapshot, ["destroy", "--help"], obj=plugin_manager)
    assert result.exit_code == 0
    assert "Destroy snapshots" in result.output


# =============================================================================
# _classify_mixed_identifiers tests
# =============================================================================


def test_classify_mixed_identifiers_empty_input_returns_empty_lists(
    temp_mngr_ctx: MngrContext,
) -> None:
    """Empty identifier list returns two empty lists."""
    agent_ids, host_ids = _classify_mixed_identifiers([], temp_mngr_ctx)
    assert agent_ids == []
    assert host_ids == []


def test_classify_mixed_identifiers_no_agents_treats_all_as_hosts(
    temp_mngr_ctx: MngrContext,
) -> None:
    """When no agents exist, all identifiers are classified as host identifiers."""
    agent_ids, host_ids = _classify_mixed_identifiers(["foo", "bar"], temp_mngr_ctx)
    assert agent_ids == []
    assert host_ids == ["foo", "bar"]
