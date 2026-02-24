from typing import Any

from imbue.mng import hookimpl

# Shell command passed to `sh -c` that opens a new iTerm2 tab and runs `mng conn`.
# MNG_AGENT_NAME is set in the environment by run_connect_command before exec.
_ITERM2_CONNECT_COMMAND = (
    'osascript -e "\n'
    '  tell application \\"iTerm2\\"\n'
    "    tell current window\n"
    "      create tab with default profile\n"
    "      tell current session\n"
    '        write text \\"mng conn $MNG_AGENT_NAME\\"\n'
    "      end tell\n"
    "    end tell\n"
    "  end tell\n"
    '"'
)

_COMMANDS_WITH_CONNECT = frozenset(("create", "start"))


@hookimpl
def override_command_options(
    command_name: str,
    command_class: type,
    params: dict[str, Any],
) -> None:
    """Override connect_command for create and start to open a new iTerm2 tab."""
    if command_name not in _COMMANDS_WITH_CONNECT:
        return
    if params.get("connect_command") is None:
        params["connect_command"] = _ITERM2_CONNECT_COMMAND
