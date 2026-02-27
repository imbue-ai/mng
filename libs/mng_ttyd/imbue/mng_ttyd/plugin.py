from typing import Any

from imbue.mng import hookimpl

TTYD_WINDOW_NAME = "ttyd"
TTYD_SERVER_NAME = "ttyd"

# Bash wrapper that starts ttyd on a random port (-p 0), watches its stderr for
# the assigned port number, and writes a servers.jsonl record so the changelings
# forwarding server can discover it. The wrapper stays alive as long as ttyd does.
TTYD_COMMAND = (
    "ttyd -p 0 bash 2>&1 | "
    "while IFS= read -r line; do "
    'echo "$line" >&2; '
    'if echo "$line" | grep -q "Listening on port:"; then '
    '_PORT=$(echo "$line" | awk '
    "'{print $NF}'); "
    'if [ -n "$MNG_AGENT_STATE_DIR" ] && [ -n "$_PORT" ]; then '
    'mkdir -p "$MNG_AGENT_STATE_DIR/logs" && '
    'printf \'{"server":"' + TTYD_SERVER_NAME + '","url":"http://127.0.0.1:%s"}\\n\' '
    '"$_PORT" >> "$MNG_AGENT_STATE_DIR/logs/servers.jsonl"; '
    "fi; fi; done"
)


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
