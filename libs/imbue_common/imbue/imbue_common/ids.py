from typing import Any
from typing import Self
from uuid import UUID
from uuid import uuid4

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema
from pydantic_core import core_schema


class InvalidRandomIdError(ValueError):
    """Raised when a RandomId value is invalid."""


class RandomId(str):
    """Base class for unique identifiers using UUID4-based hex strings with optional prefixes."""

    PREFIX: str = ""

    def __new__(cls, value: str | None = None) -> Self:
        if value is None:
            value = cls._generate()
        else:
            cls._validate(value)
        return super().__new__(cls, value)

    @classmethod
    def _validate(cls, value: str) -> None:
        """Validate that the value matches the expected format for this RandomId type."""
        if cls.PREFIX:
            expected_prefix = f"{cls.PREFIX}-"
            if not value.startswith(expected_prefix):
                raise InvalidRandomIdError(f"{cls.__name__} must start with '{expected_prefix}', got '{value}'")
            hex_part = value[len(expected_prefix) :]
        else:
            hex_part = value

        if len(hex_part) != 32:
            raise InvalidRandomIdError(f"{cls.__name__} hex part must be exactly 32 characters, got {len(hex_part)}")

        try:
            int(hex_part, 16)
        except ValueError as e:
            raise InvalidRandomIdError(
                f"{cls.__name__} hex part must contain only hexadecimal characters (0-9, a-f), got '{hex_part}'"
            ) from e

    @classmethod
    def _generate(cls) -> str:
        random_part = uuid4().hex
        if cls.PREFIX:
            return f"{cls.PREFIX}-{random_part}"
        return random_part

    @classmethod
    def generate(cls) -> Self:
        return cls(cls._generate())

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )

    def get_uuid(self) -> UUID:
        """Get the UUID representation of the RandomId."""
        if self.PREFIX:
            hex_part = self[len(self.PREFIX) + 1 :]
        else:
            hex_part = self
        return UUID(hex=hex_part)
