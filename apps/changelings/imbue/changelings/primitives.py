import re
from typing import Final
from typing import Self

from pydantic import SecretStr

from imbue.imbue_common.primitives import NonEmptyStr

_CHANGELING_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class ChangelingName(NonEmptyStr):
    """Human-readable name for a changeling agent.

    Only allows alphanumeric characters, hyphens, and underscores.
    Must start with an alphanumeric character.
    """

    def __new__(cls, value: str) -> Self:
        stripped = NonEmptyStr.__new__(cls, value)
        if not _CHANGELING_NAME_PATTERN.match(stripped):
            raise ValueError(
                f"Changeling name must contain only alphanumeric characters, hyphens, and underscores "
                f"(and start with an alphanumeric character), got: {value!r}"
            )
        return stripped


class OneTimeCode(NonEmptyStr):
    """A single-use authentication code for changeling access."""

    ...


class CookieSigningKey(SecretStr):
    """Secret key used for signing authentication cookies."""

    ...
