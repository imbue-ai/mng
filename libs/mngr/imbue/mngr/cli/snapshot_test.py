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


def test_snapshot_bare_invocation_defaults_to_create() -> None:
    """Running `mngr snapshot` with no args should forward to `snapshot create`,
    not show help or error with 'Missing command'."""
    runner = CliRunner()
    result = runner.invoke(snapshot, [])
    # The command will fail (no plugin manager context), but it should NOT
    # show group help or say "Missing command" -- it should attempt to run create.
    assert "Missing command" not in result.output
    assert "Commands:" not in result.output


def test_snapshot_unrecognized_subcommand_forwards_to_create() -> None:
    """Running `mngr snapshot my-agent` should forward to `snapshot create my-agent`."""
    runner = CliRunner()
    # "my-agent" is not a known subcommand (create/list/destroy), so it should
    # be forwarded to create as the first positional arg. The command will fail
    # (no real provider context), but the error should come from snapshot create,
    # not from "No such command 'my-agent'".
    result = runner.invoke(snapshot, ["my-agent"])
    assert "No such command" not in result.output


def test_snapshot_explicit_create_still_works() -> None:
    """Running `mngr snapshot create --help` should still work."""
    runner = CliRunner()
    result = runner.invoke(snapshot, ["create", "--help"])
    assert result.exit_code == 0
    assert "Create a snapshot" in result.output


def test_snapshot_list_subcommand_not_forwarded() -> None:
    """Running `mngr snapshot list` should NOT be forwarded to create."""
    runner = CliRunner()
    result = runner.invoke(snapshot, ["list", "--help"])
    assert result.exit_code == 0
    assert "List snapshots" in result.output


def test_snapshot_destroy_subcommand_not_forwarded() -> None:
    """Running `mngr snapshot destroy` should NOT be forwarded to create."""
    runner = CliRunner()
    result = runner.invoke(snapshot, ["destroy", "--help"])
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
