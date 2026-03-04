import platform
import subprocess

from loguru import logger


def send_desktop_notification(title: str, message: str) -> None:
    """Send a desktop notification using native OS facilities.

    On macOS, uses osascript (Notification Center).
    On Linux, uses notify-send (libnotify).
    """
    system = platform.system()
    if system == "Darwin":
        _send_macos_notification(title, message)
    elif system == "Linux":
        _send_linux_notification(title, message)
    else:
        logger.warning("Desktop notifications not supported on {}", system)


def _escape_applescript_string(s: str) -> str:
    """Escape a string for use inside AppleScript double quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _send_macos_notification(title: str, message: str) -> None:
    """Send a notification on macOS using osascript."""
    escaped_title = _escape_applescript_string(title)
    escaped_message = _escape_applescript_string(message)
    script = f'display notification "{escaped_message}" with title "{escaped_title}"'
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError:
        logger.warning("osascript not found; cannot send notification")
    except subprocess.TimeoutExpired:
        logger.warning("Notification timed out")


def _send_linux_notification(title: str, message: str) -> None:
    """Send a notification on Linux using notify-send."""
    try:
        subprocess.run(
            ["notify-send", title, message],
            check=False,
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError:
        logger.warning("notify-send not found; install libnotify to enable notifications")
    except subprocess.TimeoutExpired:
        logger.warning("Notification timed out")
