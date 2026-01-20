from enum import StrEnum


class UpperCaseStrEnum(StrEnum):
    """A StrEnum that automatically converts enum member names to uppercase values."""

    @staticmethod
    def _generate_next_value_(
        name: str,
        start: int,
        count: int,
        last_values: list[str],
    ) -> str:
        return name.upper()
