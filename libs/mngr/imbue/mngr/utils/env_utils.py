import sys

import deal


def is_interactive_terminal() -> bool:
    """Check if stdout is an interactive terminal.

    Returns False if stdout is not available (e.g., in some test environments).
    """
    try:
        return sys.stdout.isatty()
    except (ValueError, AttributeError):
        # Handle cases where stdout is uninitialized (e.g., xdist workers)
        return False


@deal.has()
def parse_env_file(content: str) -> dict[str, str]:
    """Parse an environment file into a dict."""
    env: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            else:
                # Unquoted value - use as-is
                pass
            env[key.strip()] = value
    return env
