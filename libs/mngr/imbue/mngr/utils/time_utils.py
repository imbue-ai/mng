from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ParseSpecError

_DURATION_SUFFIXES: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


@pure
def parse_duration_seconds(value: str) -> int:
    """Parse a duration string into seconds.

    Accepts either a plain integer (treated as seconds) or a number followed
    by a suffix: s (seconds), m (minutes), h (hours), d (days).

    Examples: "300", "30s", "5m", "1h", "2d"

    Raises ParseSpecError if the value cannot be parsed.
    """
    if not value:
        raise ParseSpecError("Duration cannot be empty")

    suffix = value[-1].lower()
    if suffix in _DURATION_SUFFIXES:
        number_part = value[:-1]
        if not number_part:
            raise ParseSpecError(f"Duration '{value}' is missing a number before the suffix")
        try:
            return int(number_part) * _DURATION_SUFFIXES[suffix]
        except ValueError as e:
            raise ParseSpecError(f"Duration '{value}' has an invalid number: {number_part}") from e

    try:
        return int(value)
    except ValueError as e:
        valid_suffixes = ", ".join(_DURATION_SUFFIXES.keys())
        raise ParseSpecError(
            f"Duration '{value}' is not a valid integer or duration string (valid suffixes: {valid_suffixes})"
        ) from e
