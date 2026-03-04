from abc import ABC
from abc import abstractmethod

from imbue.imbue_common.pure import pure


class TerminalApp(ABC):
    """A terminal application that can open a new tab and run a command."""

    @abstractmethod
    def build_connect_command(self, mng_connect: str, agent_name: str) -> str:
        """Build a shell command that opens a terminal tab running the given command.

        If a tab already connected to this agent exists, implementations may
        activate it instead of creating a new one.
        """


class ITermApp(TerminalApp):
    """iTerm2 on macOS. Finds an existing tab connected to the agent, or opens a new one."""

    def build_connect_command(self, mng_connect: str, agent_name: str) -> str:
        escaped_cmd = _escape_for_applescript(mng_connect)
        escaped_name = _escape_for_applescript(agent_name)
        # Search all windows/tabs for one whose session name contains the agent name.
        # If found, select that tab and activate the window. Otherwise, create a new
        # tab and run the connect command.
        return (
            "osascript"
            " -e 'tell app \"iTerm2\"'"
            " -e 'set found to false'"
            " -e 'repeat with w in windows'"
            " -e 'repeat with t in tabs of w'"
            f" -e 'if name of current session of t contains \"{escaped_name}\" then'"
            " -e 'select t'"
            " -e 'set index of w to 1'"
            " -e 'set found to true'"
            " -e 'exit repeat'"
            " -e 'end if'"
            " -e 'end repeat'"
            " -e 'if found then exit repeat'"
            " -e 'end repeat'"
            " -e 'if not found then'"
            " -e 'if (count of windows) is 0 then'"
            " -e 'create window with default profile'"
            " -e 'else'"
            " -e 'tell current window'"
            " -e 'create tab with default profile'"
            " -e 'end tell'"
            " -e 'end if'"
            " -e 'tell current session of current window'"
            f" -e 'write text \"{escaped_cmd}\"'"
            " -e 'end tell'"
            " -e 'end if'"
            " -e 'activate'"
            " -e 'end tell'"
        )


class TerminalDotApp(TerminalApp):
    """Terminal.app on macOS. Opens a new window via AppleScript."""

    def build_connect_command(self, mng_connect: str, agent_name: str) -> str:
        escaped = _escape_for_applescript(mng_connect)
        return f'osascript -e \'tell app "Terminal" to do script "{escaped}"\''


class WezTermApp(TerminalApp):
    """WezTerm. Spawns a new tab via its CLI."""

    def build_connect_command(self, mng_connect: str, agent_name: str) -> str:
        return f"wezterm cli spawn -- {mng_connect}"


class KittyApp(TerminalApp):
    """Kitty. Launches a new tab via its remote control CLI."""

    def build_connect_command(self, mng_connect: str, agent_name: str) -> str:
        return f"kitty @ launch --type=tab -- {mng_connect}"


_TERMINAL_APPS: dict[str, TerminalApp] = {
    "iterm": ITermApp(),
    "iterm2": ITermApp(),
    "terminal": TerminalDotApp(),
    "terminal.app": TerminalDotApp(),
    "wezterm": WezTermApp(),
    "kitty": KittyApp(),
}


def get_terminal_app(name: str) -> TerminalApp | None:
    """Look up a terminal app by name (case-insensitive). Returns None if unsupported."""
    return _TERMINAL_APPS.get(name.lower())


@pure
def _escape_for_applescript(s: str) -> str:
    """Escape a string for use inside AppleScript double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')
