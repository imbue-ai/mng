from imbue.imbue_common.pure import pure
from imbue.mngr.errors import ParseSpecError

_DURATION_SUFFIXES: dict[str, int] = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


# FIXME: we probably should just use a library for this. In particular, we should convert *all* places where we accept durations to use this function for converting from strings into a number of seconds
#  and then we can be sure that we're consistent about how we parse durations across the board.
#  we probably want to support every sensible format, like "5s", "5 seconds", "5 sec", "5m", "5 minutes", "5 min", etc, so find a nice library, and then convert all of the existing code to use it.
#  to be clear--all of our *internal* durations should be in seconds (float), but we should be flexible about the durations we accept from users (e.g. in config files, command line arguments, etc) and allow those to be in any sane form.
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
