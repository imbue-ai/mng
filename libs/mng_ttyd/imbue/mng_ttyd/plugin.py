from typing import Any

from imbue.mng import hookimpl

TTYD_COMMAND = "ttyd bash"
TTYD_WINDOW_NAME = "ttyd"


@hookimpl
def override_command_options(
    command_name: str,
    command_class: type,
    params: dict[str, Any],
) -> None:
    """Add a ttyd web terminal server as an additional command when creating agents."""
    if command_name != "create":
        return

    existing = params.get("add_command", ())
    params["add_command"] = (*existing, f'{TTYD_WINDOW_NAME}="{TTYD_COMMAND}"')
