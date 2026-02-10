import shlex

from imbue.imbue_common.pure import pure


@pure
def build_tmux_shell_cmd(tmux_socket_name: str | None, subcmd: str) -> str:
    """Build a tmux shell command string with optional socket name.

    The subcmd is the full tmux subcommand string (already formatted/quoted).
    Example: build_tmux_shell_cmd("mngr-test", "list-panes -s -t 'my-session'")
    """
    if tmux_socket_name:
        return f"tmux -L {shlex.quote(tmux_socket_name)} {subcmd}"
    return f"tmux {subcmd}"


@pure
def build_tmux_args(tmux_socket_name: str | None, *args: str) -> list[str]:
    """Build tmux subprocess argument list with optional socket name.

    Example: build_tmux_args("mngr-test", "has-session", "-t", "my-session")
    """
    if tmux_socket_name:
        return ["tmux", "-L", tmux_socket_name, *args]
    return ["tmux", *args]
