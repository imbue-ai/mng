"""Unit tests for plugin lifecycle hooks (on_startup, on_shutdown, on_before_command, etc.)."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import click
import pluggy
from click.testing import CliRunner

import imbue.mngr.main
from imbue.mngr import hookimpl
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.main import AliasAwareGroup
from imbue.mngr.main import reset_plugin_manager
from imbue.mngr.plugins import hookspecs

# Module-level container to capture hook invocations from test plugins.
_hook_log: list[str] = []
_hook_data: dict[str, Any] = {}


class _LifecycleTracker:
    """A test plugin that records lifecycle hook invocations."""

    @hookimpl
    def on_startup(self) -> None:
        _hook_log.append("on_startup")

    @hookimpl
    def on_shutdown(self) -> None:
        _hook_log.append("on_shutdown")

    @hookimpl
    def on_before_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        _hook_log.append("on_before_command")
        _hook_data["before_command_name"] = command_name
        _hook_data["before_command_params"] = command_params

    @hookimpl
    def on_after_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        _hook_log.append("on_after_command")
        _hook_data["after_command_name"] = command_name
        _hook_data["after_command_params"] = command_params

    @hookimpl
    def on_error(self, command_name: str, command_params: dict[str, Any], error: BaseException) -> None:
        _hook_log.append("on_error")
        _hook_data["error_command_name"] = command_name
        _hook_data["error"] = error


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
        raise RuntimeError("deliberate failure")

    test_cli.add_command(noino_cmd)
    test_cli.add_command(failing_cmd)

    try:
        yield test_cli
    finally:
        imbue.mngr.main._plugin_manager_container["pm"] = old_pm


# --- Tests ---


def test_on_startup_called_on_cli_invocation() -> None:
    """on_startup fires when the CLI group is invoked."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        assert "on_startup" in _hook_log


def test_on_shutdown_called_after_cli_completes() -> None:
    """on_shutdown fires when the CLI context closes."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        assert "on_shutdown" in _hook_log


def test_on_before_command_called_with_correct_name() -> None:
    """on_before_command receives the command name."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        assert "on_before_command" in _hook_log
        assert _hook_data.get("before_command_name") == "noino"


def test_on_before_command_receives_params_dict() -> None:
    """on_before_command receives a dict of command parameters."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        params = _hook_data.get("before_command_params")
        assert isinstance(params, dict)
        # The params dict should contain at least the common option keys
        assert "output_format" in params


def test_on_after_command_called_on_success() -> None:
    """on_after_command fires after a successful command."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        assert "on_after_command" in _hook_log
        assert _hook_data.get("after_command_name") == "noino"


def test_on_after_command_not_called_on_error() -> None:
    """on_after_command does NOT fire when a command raises."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["failing"])

        assert "on_after_command" not in _hook_log


def test_on_error_called_when_command_raises() -> None:
    """on_error fires when a command raises an exception."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["failing"])

        assert "on_error" in _hook_log
        assert _hook_data.get("error_command_name") == "failing"
        assert isinstance(_hook_data.get("error"), RuntimeError)


def test_on_error_not_called_on_success() -> None:
    """on_error does NOT fire when a command succeeds."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        assert "on_error" not in _hook_log


def test_lifecycle_hook_ordering() -> None:
    """Hooks fire in the correct order: startup, before, after, shutdown."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["noino"])

        assert _hook_log == ["on_startup", "on_before_command", "on_after_command", "on_shutdown"]


def test_lifecycle_hook_ordering_on_error() -> None:
    """On error: startup, before, error, shutdown (no after)."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        runner.invoke(test_cli, ["failing"])

        assert _hook_log == ["on_startup", "on_before_command", "on_error", "on_shutdown"]


def test_on_before_command_can_abort_execution() -> None:
    """A plugin raising in on_before_command aborts the command."""
    _hook_log.clear()
    _hook_data.clear()
    with _test_cli_with_plugins([_AbortingPlugin(), _LifecycleTracker()]) as test_cli:
        runner = CliRunner()
        result = runner.invoke(test_cli, ["noino"])

        # The command should have been aborted (non-zero exit or Abort)
        assert result.exit_code != 0
        # on_after_command should NOT have fired since the command was aborted
        assert "on_after_command" not in _hook_log
