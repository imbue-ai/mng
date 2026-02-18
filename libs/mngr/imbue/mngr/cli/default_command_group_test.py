import click
import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.default_command_group import DefaultCommandGroup
from imbue.mngr.cli.snapshot import snapshot
from imbue.mngr.main import cli

# =============================================================================
# DefaultCommandGroup tests
# =============================================================================
#
# These tests exercise the default-to-create and unrecognized-command-forwarding
# behavior using a minimal group with "create" and "list" subcommands.
# Commands store their invocation info in a shared dict so tests can verify
# routing without producing stdout output (banned by ratchet rules).


def _make_test_group(invocation_record: dict[str, str | None]) -> click.Group:
    """Build a minimal DefaultCommandGroup with 'create' and 'list' subcommands."""

    @click.group(cls=DefaultCommandGroup)
    def group() -> None:
        pass

    @group.command(name="create")
    @click.argument("name", required=False)
    def create_cmd(name: str | None) -> None:
        invocation_record["command"] = "create"
        invocation_record["name"] = name

    @group.command(name="list")
    def list_cmd() -> None:
        invocation_record["command"] = "list"

    return group


def test_bare_invocation_defaults_to_create() -> None:
    """Running the group with no args should forward to 'create'."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, [])
    assert result.exit_code == 0
    assert record["command"] == "create"


def test_unrecognized_command_forwards_to_create() -> None:
    """Running the group with an unrecognized command should forward to 'create'."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, ["my-task"])
    assert result.exit_code == 0
    assert record["command"] == "create"
    assert record["name"] == "my-task"


def test_recognized_command_not_forwarded() -> None:
    """Running the group with a recognized command should NOT be forwarded to create."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, ["list"])
    assert result.exit_code == 0
    assert record["command"] == "list"


def test_explicit_create_still_works() -> None:
    """Running 'create' explicitly should still work normally."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, ["create", "my-agent"])
    assert result.exit_code == 0
    assert record["command"] == "create"
    assert record["name"] == "my-agent"


def test_implicit_forward_meta_key() -> None:
    """When _implicit_forward_meta_key is set, the forwarded arg is stored in ctx.meta."""

    class TrackingGroup(DefaultCommandGroup):
        _implicit_forward_meta_key = "_test_implicit"

    meta_capture: dict[str, str] = {}

    @click.group(cls=TrackingGroup)
    @click.pass_context
    def group(ctx: click.Context) -> None:
        pass

    @group.command(name="create")
    @click.argument("name", required=False)
    @click.pass_context
    def create_cmd(ctx: click.Context, name: str | None) -> None:
        parent_meta = ctx.parent.meta if ctx.parent else {}
        if "_test_implicit" in parent_meta:
            meta_capture["forwarded_arg"] = parent_meta["_test_implicit"]

    runner = CliRunner()
    result = runner.invoke(group, ["my-typo"])
    assert result.exit_code == 0
    assert meta_capture["forwarded_arg"] == "my-typo"


# =============================================================================
# Integration tests: real mngr CLI defaults to create
# =============================================================================


def test_mngr_bare_invocation_defaults_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr` with no args should forward to `mngr create`."""
    result = cli_runner.invoke(cli, [], obj=plugin_manager)
    # create with no args should attempt to create an agent (not show group help)
    assert "Missing command" not in result.output
    assert "Commands:" not in result.output


def test_mngr_unrecognized_command_forwards_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr my-task` should forward to `mngr create my-task`."""
    result = cli_runner.invoke(cli, ["my-task"], obj=plugin_manager)
    assert "No such command" not in result.output


def test_mngr_snapshot_bare_defaults_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr snapshot` with no args should forward to `snapshot create`."""
    result = cli_runner.invoke(snapshot, [], obj=plugin_manager)
    assert "Missing command" not in result.output
    assert "Commands:" not in result.output
    assert "Must specify at least one agent" in result.output


def test_mngr_snapshot_unrecognized_forwards_to_create(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Running `mngr snapshot nonexistent` should forward to `snapshot create nonexistent`."""
    result = cli_runner.invoke(snapshot, ["nonexistent"], obj=plugin_manager)
    assert "No such command" not in result.output
