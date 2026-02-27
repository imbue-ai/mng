from typing import Any

from imbue.mng import hookimpl

TTYD_WINDOW_NAME = "ttyd"
TTYD_SERVER_NAME = "ttyd"

# Python one-liner that binds to port 0 (OS assigns a free port) and prints it.
_FIND_PORT_PYTHON = "import socket;s=socket.socket();s.bind(('',0));print(s.getsockname()[1]);s.close()"

# Shell command that finds a free port and stores it in $PORT.
_FIND_PORT_CMD = f'PORT=$(python3 -c "{_FIND_PORT_PYTHON}")'

# Shell command that writes a servers.jsonl record if MNG_AGENT_STATE_DIR is set.
# This allows the changelings forwarding server to discover and route to the ttyd instance.
_WRITE_SERVER_LOG_CMD = (
    'if [ -n "$MNG_AGENT_STATE_DIR" ]; then '
    'mkdir -p "$MNG_AGENT_STATE_DIR/logs" && '
    'printf \'{"server":"' + TTYD_SERVER_NAME + '","url":"http://127.0.0.1:%s"}\\n\' '
    '"$PORT" >> "$MNG_AGENT_STATE_DIR/logs/servers.jsonl"; fi'
)

# Shell command that execs ttyd on the port stored in $PORT.
_EXEC_TTYD_CMD = 'exec ttyd -p "$PORT" bash'

# Full command: find a free port, log it to servers.jsonl, and start ttyd on that port.
TTYD_COMMAND = f"{_FIND_PORT_CMD} && {_WRITE_SERVER_LOG_CMD} && {_EXEC_TTYD_CMD}"


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
