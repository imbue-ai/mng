"""Unit tests for plugin lifecycle hooks (on_startup, on_shutdown, on_before_command, etc.)."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import click
import pluggy
import pytest
from click.testing import CliRunner

import imbue.mngr.main
from imbue.mngr import hookimpl
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.main import AliasAwareGroup
from imbue.mngr.main import reset_plugin_manager
from imbue.mngr.plugins import hookspecs


class _LifecycleTracker:
    """A test plugin that records lifecycle hook invocations."""

    def __init__(self) -> None:
        # Real plugins are plain classes with no __init__ (just @hookimpl methods).
        # We need __init__ here to hold per-instance test state.
        self.hook_log: list[str] = []
        self.hook_data: dict[str, Any] = {}

    @hookimpl
    def on_startup(self) -> None:
        self.hook_log.append("on_startup")

    @hookimpl
    def on_shutdown(self) -> None:
        self.hook_log.append("on_shutdown")

    @hookimpl
    def on_before_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        self.hook_log.append("on_before_command")
        self.hook_data["before_command_name"] = command_name
        self.hook_data["before_command_params"] = command_params

    @hookimpl
    def on_after_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        self.hook_log.append("on_after_command")
        self.hook_data["after_command_name"] = command_name
        self.hook_data["after_command_params"] = command_params

    @hookimpl
    def on_error(self, command_name: str, command_params: dict[str, Any], error: BaseException) -> None:
        self.hook_log.append("on_error")
        self.hook_data["error_command_name"] = command_name
        self.hook_data["error"] = error


class _AbortingPlugin:
    """A test plugin that aborts execution by raising in on_before_command."""

    @hookimpl
    def on_before_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        raise click.Abort()


class _NoinoCliOptions(CommonCliOptions):
    """Minimal options class for the test 'noino' command."""


class _FailingCliOptions(CommonCliOptions):
    """Minimal options class for the test 'failing' command."""


@contextmanager
def _test_cli_with_plugins(
    plugins: list[Any],
) -> Generator[click.Group, None, None]:
    """Create an AliasAwareGroup-based test CLI with lifecycle-tracking plugins."""
    reset_plugin_manager()
    pm = pluggy.PluginManager("mngr")
    pm.add_hookspecs(hookspecs)
    for plugin in plugins:
        pm.register(plugin)

    old_pm = imbue.mngr.main._plugin_manager_container["pm"]
    imbue.mngr.main._plugin_manager_container["pm"] = pm

    @click.command(cls=AliasAwareGroup)
    @click.pass_context
    def test_cli(ctx: click.Context) -> None:
        ctx.obj = pm
        pm.hook.on_startup()
        ctx.call_on_close(lambda: pm.hook.on_shutdown())

    @click.command(name="noino")
    @add_common_options
    @click.pass_context
    def noino_cmd(ctx: click.Context, **kwargs: Any) -> None:
        """A simple test command that does nothing."""
        setup_command_context(ctx=ctx, command_name="noino", command_class=_NoinoCliOptions)

    @click.command(name="failing")
    @add_common_options
    @click.pass_context
    def failing_cmd(ctx: click.Context, **kwargs: Any) -> None:
        """A test command that raises an error after setup."""
        setup_command_context(ctx=ctx, command_name="failing", command_class=_FailingCliOptions)
        raise PluginMngrError("deliberate failure")

    test_cli.add_command(noino_cmd)
    test_cli.add_command(failing_cmd)

    try:
        yield test_cli
    finally:
        imbue.mngr.main._plugin_manager_container["pm"] = old_pm


class _LifecycleFixture:
    """Container for the shared lifecycle test state."""

    def __init__(self, tracker: _LifecycleTracker, cli: click.Group, runner: CliRunner) -> None:
        self.tracker = tracker
        self.cli = cli
        self.runner = runner

    @property
    def hook_log(self) -> list[str]:
        return self.tracker.hook_log

    @property
    def hook_data(self) -> dict[str, Any]:
        return self.tracker.hook_data


@pytest.fixture()
def lifecycle_fixture() -> Generator[_LifecycleFixture, None, None]:
    """Provide a test CLI with a lifecycle-tracking plugin and a runner."""
    tracker = _LifecycleTracker()
    with _test_cli_with_plugins([tracker]) as cli:
        yield _LifecycleFixture(tracker=tracker, cli=cli, runner=CliRunner())


# --- Tests ---


def test_on_startup_called_on_cli_invocation(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_startup fires when the CLI group is invoked."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    assert "on_startup" in lifecycle_fixture.hook_log


def test_on_shutdown_called_after_cli_completes(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_shutdown fires when the CLI context closes."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    assert "on_shutdown" in lifecycle_fixture.hook_log


def test_on_before_command_called_with_correct_name(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_before_command receives the command name."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    assert "on_before_command" in lifecycle_fixture.hook_log
    assert lifecycle_fixture.hook_data.get("before_command_name") == "noino"


def test_on_before_command_receives_params_dict(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_before_command receives a dict of command parameters."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    params = lifecycle_fixture.hook_data.get("before_command_params")
    assert isinstance(params, dict)
    # The params dict should contain at least the common option keys
    assert "output_format" in params


def test_on_after_command_called_on_success(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_after_command fires after a successful command."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    assert "on_after_command" in lifecycle_fixture.hook_log
    assert lifecycle_fixture.hook_data.get("after_command_name") == "noino"


def test_on_after_command_not_called_on_error(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_after_command does NOT fire when a command raises."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["failing"])

    assert "on_after_command" not in lifecycle_fixture.hook_log


def test_on_error_called_when_command_raises(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_error fires when a command raises an exception."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["failing"])

    assert "on_error" in lifecycle_fixture.hook_log
    assert lifecycle_fixture.hook_data.get("error_command_name") == "failing"
    assert isinstance(lifecycle_fixture.hook_data.get("error"), PluginMngrError)


def test_on_error_not_called_on_success(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_error does NOT fire when a command succeeds."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    assert "on_error" not in lifecycle_fixture.hook_log


def test_lifecycle_hook_ordering(lifecycle_fixture: _LifecycleFixture) -> None:
    """Hooks fire in the correct order: startup, before, after, shutdown."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["noino"])

    assert lifecycle_fixture.hook_log == ["on_startup", "on_before_command", "on_after_command", "on_shutdown"]


def test_lifecycle_hook_ordering_on_error(lifecycle_fixture: _LifecycleFixture) -> None:
    """On error: startup, before, error, shutdown (no after)."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["failing"])

    assert lifecycle_fixture.hook_log == ["on_startup", "on_before_command", "on_error", "on_shutdown"]


def test_on_before_command_can_abort_execution() -> None:
    """A plugin raising in on_before_command aborts the command."""
    tracker = _LifecycleTracker()
    with _test_cli_with_plugins([_AbortingPlugin(), tracker]) as cli:
        runner = CliRunner()
        result = runner.invoke(cli, ["noino"])

        # The command should have been aborted (non-zero exit or Abort)
        assert result.exit_code != 0
        # on_after_command should NOT have fired since the command was aborted
        assert "on_after_command" not in tracker.hook_log
