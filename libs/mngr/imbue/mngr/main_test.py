import click
from click.testing import CliRunner

from imbue.mngr.main import AliasAwareGroup

# =============================================================================
# AliasAwareGroup tests
# =============================================================================
#
# These tests exercise the default-to-create and unrecognized-command-forwarding
# behavior using a minimal group with "create" and "list" subcommands.
# Commands store their invocation info in a shared dict so tests can verify
# routing without producing stdout output (banned by ratchet rules).


def _make_test_group(invocation_record: dict[str, str | None]) -> click.Group:
    """Build a minimal AliasAwareGroup with 'create' and 'list' subcommands."""

    @click.group(cls=AliasAwareGroup)
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


def test_alias_aware_group_bare_invocation_defaults_to_create() -> None:
    """Running the group with no args should forward to 'create'."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, [])
    assert result.exit_code == 0
    assert record["command"] == "create"


def test_alias_aware_group_unrecognized_command_forwards_to_create() -> None:
    """Running the group with an unrecognized command should forward to 'create'."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, ["my-task"])
    assert result.exit_code == 0
    assert record["command"] == "create"
    assert record["name"] == "my-task"


def test_alias_aware_group_recognized_command_not_forwarded() -> None:
    """Running the group with a recognized command should NOT be forwarded to create."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, ["list"])
    assert result.exit_code == 0
    assert record["command"] == "list"


def test_alias_aware_group_explicit_create_still_works() -> None:
    """Running 'create' explicitly should still work normally."""
    record: dict[str, str | None] = {}
    group = _make_test_group(record)
    runner = CliRunner()
    result = runner.invoke(group, ["create", "my-agent"])
    assert result.exit_code == 0
    assert record["command"] == "create"
    assert record["name"] == "my-agent"
