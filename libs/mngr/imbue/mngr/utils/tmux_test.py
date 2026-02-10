"""Unit tests for tmux helper utilities."""

from imbue.mngr.utils.tmux import build_tmux_args
from imbue.mngr.utils.tmux import build_tmux_shell_cmd

# =============================================================================
# build_tmux_shell_cmd
# =============================================================================


def test_build_tmux_shell_cmd_with_socket() -> None:
    """Socket name is inserted as -L flag."""
    result = build_tmux_shell_cmd("mngr-test", "list-panes -s -t 'my-session'")
    assert result == "tmux -L mngr-test list-panes -s -t 'my-session'"


def test_build_tmux_shell_cmd_without_socket() -> None:
    """None socket name produces plain tmux command."""
    result = build_tmux_shell_cmd(None, "list-sessions -F '#{session_name}'")
    assert result == "tmux list-sessions -F '#{session_name}'"


def test_build_tmux_shell_cmd_empty_string_socket() -> None:
    """Empty string socket name is treated as no socket (falsy)."""
    result = build_tmux_shell_cmd("", "has-session -t foo")
    assert result == "tmux has-session -t foo"


def test_build_tmux_shell_cmd_with_hyphenated_socket() -> None:
    """Socket names with hyphens work correctly."""
    result = build_tmux_shell_cmd("my-socket", "list-sessions")
    assert result == "tmux -L my-socket list-sessions"


# =============================================================================
# build_tmux_args
# =============================================================================


def test_build_tmux_args_with_socket() -> None:
    """Socket name is inserted as -L flag in args list."""
    result = build_tmux_args("mngr-test", "has-session", "-t", "my-session")
    assert result == ["tmux", "-L", "mngr-test", "has-session", "-t", "my-session"]


def test_build_tmux_args_without_socket() -> None:
    """None socket name produces plain tmux args."""
    result = build_tmux_args(None, "kill-session", "-t", "foo")
    assert result == ["tmux", "kill-session", "-t", "foo"]


def test_build_tmux_args_empty_string_socket() -> None:
    """Empty string socket name is treated as no socket (falsy)."""
    result = build_tmux_args("", "list-sessions")
    assert result == ["tmux", "list-sessions"]


def test_build_tmux_args_no_extra_args() -> None:
    """Works with no subcommand args (just socket)."""
    result = build_tmux_args("sock")
    assert result == ["tmux", "-L", "sock"]
