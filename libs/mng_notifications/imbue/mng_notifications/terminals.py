from abc import ABC
from abc import abstractmethod

from imbue.imbue_common.pure import pure


class TerminalApp(ABC):
    """A terminal application that can open a new tab and run a command."""

    @abstractmethod
    def build_connect_command(self, mng_connect: str) -> str:
        """Build a shell command that opens a new terminal tab running the given command."""


class ITermApp(TerminalApp):
    """iTerm2 on macOS. Opens a new tab via AppleScript and types the command."""

    def build_connect_command(self, mng_connect: str) -> str:
        escaped = _escape_for_applescript(mng_connect)
        return (
            "osascript"
            " -e 'tell app \"iTerm2\"'"
            " -e 'activate'"
            " -e 'tell current window'"
            " -e 'create tab with default profile'"
            " -e 'tell current session'"
            f" -e 'write text \"{escaped}\"'"
            " -e 'end tell'"
            " -e 'end tell'"
            " -e 'end tell'"
        )


class TerminalDotApp(TerminalApp):
    """Terminal.app on macOS. Opens a new window via AppleScript."""

    def build_connect_command(self, mng_connect: str) -> str:
        escaped = _escape_for_applescript(mng_connect)
        return f'osascript -e \'tell app "Terminal" to do script "{escaped}"\''


class WezTermApp(TerminalApp):
    """WezTerm. Spawns a new tab via its CLI."""

    def build_connect_command(self, mng_connect: str) -> str:
        return f"wezterm cli spawn -- {mng_connect}"


class KittyApp(TerminalApp):
    """Kitty. Launches a new tab via its remote control CLI."""

    def build_connect_command(self, mng_connect: str) -> str:
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
