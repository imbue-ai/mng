"""Unit tests for the connect_in_new_iterms2_tab built-in plugin."""

from imbue.mng.plugins import connect_in_new_iterms2_tab
from imbue.mng.plugins.connect_in_new_iterms2_tab import _ITERM2_CONNECT_COMMAND
from imbue.mng.plugins.connect_in_new_iterms2_tab import override_command_options


def test_sets_connect_command_for_create() -> None:
    """Plugin sets connect_command on the create command when none is set."""
    params: dict[str, object] = {"connect_command": None, "connect": True}
    override_command_options(command_name="create", command_class=object, params=params)
    assert params["connect_command"] == _ITERM2_CONNECT_COMMAND


def test_sets_connect_command_for_start() -> None:
    """Plugin sets connect_command on the start command when none is set."""
    params: dict[str, object] = {"connect_command": None, "connect": True}
    override_command_options(command_name="start", command_class=object, params=params)
    assert params["connect_command"] == _ITERM2_CONNECT_COMMAND


def test_does_not_override_existing_connect_command() -> None:
    """Plugin does not override a connect_command that was already set."""
    custom_command = "my-custom-connect-script"
    params: dict[str, object] = {"connect_command": custom_command, "connect": True}
    override_command_options(command_name="create", command_class=object, params=params)
    assert params["connect_command"] == custom_command


def test_does_not_affect_other_commands() -> None:
    """Plugin does not modify params for commands other than create and start."""
    params: dict[str, object] = {"connect_command": None}
    override_command_options(command_name="connect", command_class=object, params=params)
    assert params["connect_command"] is None


def test_connect_command_contains_iterm2_osascript() -> None:
    """The iTerm2 connect command contains the expected osascript invocation."""
    assert "osascript" in _ITERM2_CONNECT_COMMAND
    assert "iTerm2" in _ITERM2_CONNECT_COMMAND
    assert "create tab with default profile" in _ITERM2_CONNECT_COMMAND
    assert "mng conn $MNG_AGENT_NAME" in _ITERM2_CONNECT_COMMAND


def test_disabled_by_default() -> None:
    """Plugin declares itself as disabled by default."""
    assert connect_in_new_iterms2_tab.ENABLED_BY_DEFAULT is False
