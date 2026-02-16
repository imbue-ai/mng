import pytest

from imbue.mngr.errors import ParseSpecError
from imbue.mngr.utils.time_utils import parse_duration_seconds


def test_plain_integer() -> None:
    assert parse_duration_seconds("300") == 300


def test_seconds_suffix() -> None:
    assert parse_duration_seconds("30s") == 30


def test_minutes_suffix() -> None:
    assert parse_duration_seconds("5m") == 300


def test_hours_suffix() -> None:
    assert parse_duration_seconds("1h") == 3600


def test_days_suffix() -> None:
    assert parse_duration_seconds("2d") == 172800


def test_uppercase_suffix() -> None:
    assert parse_duration_seconds("5M") == 300


def test_empty_string_raises() -> None:
    with pytest.raises(ParseSpecError, match="cannot be empty"):
        parse_duration_seconds("")


def test_invalid_string_raises() -> None:
    with pytest.raises(ParseSpecError, match="not a valid integer"):
        parse_duration_seconds("abc")


def test_suffix_without_number_raises() -> None:
    with pytest.raises(ParseSpecError, match="missing a number"):
        parse_duration_seconds("m")


def test_invalid_number_with_suffix_raises() -> None:
    with pytest.raises(ParseSpecError, match="invalid number"):
        parse_duration_seconds("abcm")
