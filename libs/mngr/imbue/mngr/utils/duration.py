import re

from imbue.imbue_common.pure import pure
from imbue.mngr.errors import UserInputError

_DURATION_PATTERN = re.compile(
    r"(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$",
    re.IGNORECASE,
)


@pure
def parse_duration_to_seconds(duration_str: str) -> float:
    """Parse a human-readable duration string into seconds.

    Supports plain integers (treated as seconds) and combinations of
    days (d), hours (h), minutes (m), seconds (s).
    Examples: '300', '7d', '24h', '30m', '1h30m', '90s', '1d12h'.
    """
    stripped = duration_str.strip()
    if not stripped:
        raise UserInputError(f"Invalid duration: '{duration_str}' (empty string)")

    # Plain integer is treated as seconds
    try:
        plain_seconds = int(stripped)
        if plain_seconds <= 0:
            raise UserInputError(f"Invalid duration: '{duration_str}'. Duration must be greater than zero.")
        return float(plain_seconds)
    except ValueError:
        pass

    match = _DURATION_PATTERN.match(stripped)
    if match is None or match.group(0) == "":
        raise UserInputError(
            f"Invalid duration: '{duration_str}'. Expected format like '300', '7d', '24h', '30m', '90s', '1h30m', '1d12h'."
        )

    days = int(match.group(1)) if match.group(1) else 0
    hours = int(match.group(2)) if match.group(2) else 0
    minutes = int(match.group(3)) if match.group(3) else 0
    seconds = int(match.group(4)) if match.group(4) else 0

    total_seconds = float(days * 86400 + hours * 3600 + minutes * 60 + seconds)

    if total_seconds == 0.0:
        raise UserInputError(f"Invalid duration: '{duration_str}'. Duration must be greater than zero.")

    return total_seconds
