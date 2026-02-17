"""Unit tests for plugin lifecycle hooks (on_startup, on_shutdown, on_before_command, etc.)."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
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

# Module-level container for the marker file path, set by the fixture and read
# by test commands. Same pattern as _captured_values in test_plugin_cli_commands.py.
_marker_path_container: dict[str, Path | None] = {"path": None}


class _LifecycleTracker:
    """A test plugin that records lifecycle hook invocations and marker file state."""

    def __init__(self) -> None:
        # Real plugins are plain classes with no __init__ (just @hookimpl methods).
        # We need __init__ here to hold per-instance test state.
        self.hook_log: list[tuple[str, bool]] = []
        self.hook_data: dict[str, Any] = {}
        self.marker_path: Path | None = None

    def _marker_exists(self) -> bool:
        if self.marker_path is None:
            return False
        return self.marker_path.exists()

    @hookimpl
    def on_startup(self) -> None:
        self.hook_log.append(("on_startup", self._marker_exists()))

    @hookimpl
    def on_shutdown(self) -> None:
        self.hook_log.append(("on_shutdown", self._marker_exists()))

    @hookimpl
    def on_before_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        self.hook_log.append(("on_before_command", self._marker_exists()))
        self.hook_data["before_command_name"] = command_name
        self.hook_data["before_command_params"] = command_params

    @hookimpl
    def on_after_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        self.hook_log.append(("on_after_command", self._marker_exists()))
        self.hook_data["after_command_name"] = command_name
        self.hook_data["after_command_params"] = command_params

    @hookimpl
    def on_error(self, command_name: str, command_params: dict[str, Any], error: BaseException) -> None:
        self.hook_log.append(("on_error", self._marker_exists()))
        self.hook_data["error_command_name"] = command_name
        self.hook_data["error"] = error


class _AbortingPlugin:
    """A test plugin that aborts execution by raising in on_before_command."""

    @hookimpl
    def on_before_command(self, command_name: str, command_params: dict[str, Any]) -> None:
        raise click.Abort()


class _TouchCliOptions(CommonCliOptions):
    """Minimal options class for the test 'touch' command."""


class _TouchFailCliOptions(CommonCliOptions):
    """Minimal options class for the test 'touch-fail' command."""


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

    @click.command(name="touch")
    @add_common_options
    @click.pass_context
    def touch_cmd(ctx: click.Context, **kwargs: Any) -> None:
        """A test command that creates a marker file."""
        setup_command_context(ctx=ctx, command_name="touch", command_class=_TouchCliOptions)
        marker_path = _marker_path_container["path"]
        if marker_path is not None:
            marker_path.touch()

    @click.command(name="touch-fail")
    @add_common_options
    @click.pass_context
    def touch_fail_cmd(ctx: click.Context, **kwargs: Any) -> None:
        """A test command that creates a marker file then raises."""
        setup_command_context(ctx=ctx, command_name="touch-fail", command_class=_TouchFailCliOptions)
        marker_path = _marker_path_container["path"]
        if marker_path is not None:
            marker_path.touch()
        raise PluginMngrError("deliberate failure")

    test_cli.add_command(touch_cmd)
    test_cli.add_command(touch_fail_cmd)

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
    def hook_log(self) -> list[tuple[str, bool]]:
        return self.tracker.hook_log

    @property
    def hook_data(self) -> dict[str, Any]:
        return self.tracker.hook_data


@pytest.fixture()
def lifecycle_fixture(tmp_path: Path) -> Generator[_LifecycleFixture, None, None]:
    """Provide a test CLI with a lifecycle-tracking plugin and a runner."""
    tracker = _LifecycleTracker()
    marker_path = tmp_path / "marker"
    tracker.marker_path = marker_path
    _marker_path_container["path"] = marker_path
    with _test_cli_with_plugins([tracker]) as cli:
        yield _LifecycleFixture(tracker=tracker, cli=cli, runner=CliRunner())
    _marker_path_container["path"] = None


# --- Tests ---


def test_on_startup_called_on_cli_invocation(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_startup fires when the CLI group is invoked, before the marker file exists."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    assert ("on_startup", False) in lifecycle_fixture.hook_log


def test_on_shutdown_called_after_cli_completes(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_shutdown fires when the CLI context closes, after the command created the marker."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    assert ("on_shutdown", True) in lifecycle_fixture.hook_log


def test_on_before_command_called_with_correct_name(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_before_command receives the command name and fires before command work."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    assert ("on_before_command", False) in lifecycle_fixture.hook_log
    assert lifecycle_fixture.hook_data.get("before_command_name") == "touch"


def test_on_before_command_receives_params_dict(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_before_command receives a dict of command parameters."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    params = lifecycle_fixture.hook_data.get("before_command_params")
    assert isinstance(params, dict)
    # The params dict should contain at least the common option keys
    assert "output_format" in params


def test_on_after_command_called_on_success(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_after_command fires after a successful command, seeing the marker file."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    assert ("on_after_command", True) in lifecycle_fixture.hook_log
    assert lifecycle_fixture.hook_data.get("after_command_name") == "touch"


def test_on_after_command_not_called_on_error(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_after_command does NOT fire when a command raises."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch-fail"])

    hook_names = [name for name, _ in lifecycle_fixture.hook_log]
    assert "on_after_command" not in hook_names


def test_on_error_called_when_command_raises(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_error fires when a command raises, seeing the marker the command created."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch-fail"])

    assert ("on_error", True) in lifecycle_fixture.hook_log
    assert lifecycle_fixture.hook_data.get("error_command_name") == "touch-fail"
    assert isinstance(lifecycle_fixture.hook_data.get("error"), PluginMngrError)


def test_on_error_not_called_on_success(lifecycle_fixture: _LifecycleFixture) -> None:
    """on_error does NOT fire when a command succeeds."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    hook_names = [name for name, _ in lifecycle_fixture.hook_log]
    assert "on_error" not in hook_names


def test_lifecycle_hook_ordering(lifecycle_fixture: _LifecycleFixture) -> None:
    """Hooks fire in the correct order relative to command work."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch"])

    assert lifecycle_fixture.hook_log == [
        ("on_startup", False),
        ("on_before_command", False),
        ("on_after_command", True),
        ("on_shutdown", True),
    ]


def test_lifecycle_hook_ordering_on_error(lifecycle_fixture: _LifecycleFixture) -> None:
    """On error: startup, before (no file), error (file exists), shutdown."""
    lifecycle_fixture.runner.invoke(lifecycle_fixture.cli, ["touch-fail"])

    assert lifecycle_fixture.hook_log == [
        ("on_startup", False),
        ("on_before_command", False),
        ("on_error", True),
        ("on_shutdown", True),
    ]


def test_on_before_command_can_abort_execution(tmp_path: Path) -> None:
    """A plugin raising in on_before_command aborts the command and prevents file creation."""
    tracker = _LifecycleTracker()
    marker_path = tmp_path / "marker"
    tracker.marker_path = marker_path
    _marker_path_container["path"] = marker_path
    with _test_cli_with_plugins([_AbortingPlugin(), tracker]) as cli:
        runner = CliRunner()
        result = runner.invoke(cli, ["touch"])

        # The command should have been aborted (non-zero exit or Abort)
        assert result.exit_code != 0
        # on_after_command should NOT have fired since the command was aborted
        hook_names = [name for name, _ in tracker.hook_log]
        assert "on_after_command" not in hook_names
        # The marker file should not exist since command work was prevented
        assert not marker_path.exists()
    _marker_path_container["path"] = None
