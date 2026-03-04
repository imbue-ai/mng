import platform
import shlex
import subprocess

from loguru import logger

from imbue.imbue_common.pure import pure
from imbue.mng_notifications.config import NotificationsPluginConfig


def send_desktop_notification(
    title: str,
    message: str,
    agent_name: str,
    config: NotificationsPluginConfig,
) -> None:
    """Send a desktop notification, optionally with a click-to-connect action.

    On macOS, uses terminal-notifier (supports click actions).
    On Linux, uses notify-send (click actions not yet supported).
    """
    execute_command = build_execute_command(agent_name, config)

    system = platform.system()
    if system == "Darwin":
        _send_macos_notification(title, message, execute_command)
    elif system == "Linux":
        _send_linux_notification(title, message)
    else:
        logger.warning("Desktop notifications not supported on {}", system)


@pure
def build_execute_command(agent_name: str, config: NotificationsPluginConfig) -> str | None:
    """Build the shell command to run when the notification is clicked.

    Returns None if no terminal_app or custom_terminal_command is configured.
    """
    if config.custom_terminal_command is not None:
        quoted_name = shlex.quote(agent_name)
        return f"MNG_AGENT_NAME={quoted_name} {config.custom_terminal_command}"

    if config.terminal_app is None:
        return None

    return _build_terminal_app_command(agent_name, config.terminal_app)


@pure
def _build_terminal_app_command(agent_name: str, terminal_app: str) -> str | None:
    """Build a connect command for a known terminal application."""
    quoted_name = shlex.quote(agent_name)
    mng_connect = f"mng connect {quoted_name}"

    match terminal_app.lower():
        case "iterm" | "iterm2":
            # AppleScript: activate iTerm, open a new tab, and type the command.
            # Uses "write text" rather than "command" so the tab stays open in a
            # normal shell session after the command finishes.
            escaped_for_applescript = mng_connect.replace("\\", "\\\\").replace('"', '\\"')
            return (
                "osascript"
                " -e 'tell app \"iTerm2\"'"
                " -e 'activate'"
                " -e 'tell current window'"
                " -e 'create tab with default profile'"
                " -e 'tell current session'"
                f" -e 'write text \"{escaped_for_applescript}\"'"
                " -e 'end tell'"
                " -e 'end tell'"
                " -e 'end tell'"
            )
        case "terminal" | "terminal.app":
            escaped_for_applescript = mng_connect.replace("\\", "\\\\").replace('"', '\\"')
            return f'osascript -e \'tell app "Terminal" to do script "{escaped_for_applescript}"\''
        case "wezterm":
            return f"wezterm cli spawn -- {mng_connect}"
        case "kitty":
            return f"kitty @ launch --type=tab -- {mng_connect}"
        case _:
            logger.warning(
                "Unsupported terminal app: {}. Use custom_terminal_command instead.",
                terminal_app,
            )
            return None


def _send_macos_notification(title: str, message: str, execute_command: str | None) -> None:
    """Send a notification on macOS using terminal-notifier."""
    cmd = ["terminal-notifier", "-title", title, "-message", message]
    if execute_command is not None:
        cmd.extend(["-execute", execute_command])
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)
    except FileNotFoundError:
        logger.warning("terminal-notifier not found; install with: brew install terminal-notifier")
    except subprocess.TimeoutExpired:
        logger.warning("Notification timed out")


def _send_linux_notification(title: str, message: str) -> None:
    """Send a notification on Linux using notify-send."""
    try:
        subprocess.run(["notify-send", title, message], check=False, capture_output=True, timeout=10)
    except FileNotFoundError:
        logger.warning("notify-send not found; install libnotify to enable notifications")
    except subprocess.TimeoutExpired:
        logger.warning("Notification timed out")
