import re
from typing import Any
from typing import Final
from typing import Self

from pydantic import GetCoreSchemaHandler
from pydantic import SecretStr
from pydantic_core import CoreSchema
from pydantic_core import core_schema

from imbue.imbue_common.primitives import NonEmptyStr

_CHANGELING_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class ChangelingName(str):
    """Human-readable name for a changeling agent.

    Only allows alphanumeric characters, hyphens, and underscores.
    Must start with an alphanumeric character.
    """

    def __new__(cls, value: str) -> Self:
        if not value or not value.strip():
            raise ValueError("Changeling name cannot be empty")
        if not _CHANGELING_NAME_PATTERN.match(value):
            raise ValueError(
                f"Changeling name must contain only alphanumeric characters, hyphens, and underscores "
                f"(and start with an alphanumeric character), got: {value!r}"
            )
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(min_length=1),
        )


class OneTimeCode(NonEmptyStr):
    """A single-use authentication code for changeling access."""

    ...


class CookieSigningKey(SecretStr):
    """Secret key used for signing authentication cookies."""

    ...
