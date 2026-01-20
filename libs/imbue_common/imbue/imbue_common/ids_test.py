import pytest

from imbue.imbue_common.ids import InvalidRandomIdError
from imbue.imbue_common.ids import RandomId


class MyTestId(RandomId):
    PREFIX = "test"


class NoPreFixId(RandomId):
    PREFIX = ""


def test_random_id_generates_with_prefix() -> None:
    test_id = MyTestId()
    assert test_id.startswith("test-")
    parts = test_id.split("-", 1)
    assert len(parts) == 2
    hex_part = parts[1]
    assert len(hex_part) == 32
    int(hex_part, 16)


def test_random_id_generates_without_prefix() -> None:
    no_prefix_id = NoPreFixId()
    assert "-" not in no_prefix_id
    assert len(no_prefix_id) == 32
    int(no_prefix_id, 16)


def test_random_id_accepts_existing_value() -> None:
    existing_value = "test-1234567890abcdef1234567890abcdef"
    test_id = MyTestId(existing_value)
    assert test_id == existing_value
    assert str(test_id) == existing_value


def test_random_id_generate_class_method() -> None:
    test_id = MyTestId.generate()
    assert isinstance(test_id, MyTestId)
    assert test_id.startswith("test-")
    parts = test_id.split("-", 1)
    assert len(parts) == 2
    hex_part = parts[1]
    assert len(hex_part) == 32
    int(hex_part, 16)


def test_random_id_uniqueness() -> None:
    id1 = MyTestId()
    id2 = MyTestId()
    assert id1 != id2


def test_random_id_is_string_subclass() -> None:
    test_id = MyTestId()
    assert isinstance(test_id, str)
    assert isinstance(test_id, MyTestId)


def test_random_id_with_prefix_rejects_value_without_prefix() -> None:
    with pytest.raises(InvalidRandomIdError, match="must start with 'test-'"):
        MyTestId("1234567890abcdef1234567890abcdef")


def test_random_id_with_prefix_rejects_value_with_wrong_prefix() -> None:
    with pytest.raises(InvalidRandomIdError, match="must start with 'test-'"):
        MyTestId("wrong-1234567890abcdef1234567890abcdef")


def test_random_id_rejects_value_with_invalid_hex_characters() -> None:
    with pytest.raises(InvalidRandomIdError, match="must contain only hexadecimal characters"):
        MyTestId("test-1234567890abcdefghij567890abcdef")


def test_random_id_rejects_value_with_too_short_hex() -> None:
    with pytest.raises(InvalidRandomIdError, match="must be exactly 32 characters"):
        MyTestId("test-1234567890abcdef")


def test_random_id_rejects_value_with_too_long_hex() -> None:
    with pytest.raises(InvalidRandomIdError, match="must be exactly 32 characters"):
        MyTestId("test-1234567890abcdef1234567890abcdef12")


def test_random_id_without_prefix_rejects_value_with_invalid_hex_characters() -> None:
    with pytest.raises(InvalidRandomIdError, match="must contain only hexadecimal characters"):
        NoPreFixId("1234567890abcdefghij567890abcdef")


def test_random_id_without_prefix_rejects_value_with_too_short_hex() -> None:
    with pytest.raises(InvalidRandomIdError, match="must be exactly 32 characters"):
        NoPreFixId("1234567890abcdef")


def test_random_id_without_prefix_rejects_value_with_too_long_hex() -> None:
    with pytest.raises(InvalidRandomIdError, match="must be exactly 32 characters"):
        NoPreFixId("1234567890abcdef1234567890abcdef12")


def test_random_id_without_prefix_accepts_valid_hex() -> None:
    valid_hex = "1234567890abcdef1234567890abcdef"
    no_prefix_id = NoPreFixId(valid_hex)
    assert no_prefix_id == valid_hex
    assert str(no_prefix_id) == valid_hex


def test_random_id_get_uuid_with_prefix() -> None:
    """get_uuid should extract the UUID from an ID with a prefix."""
    test_id = MyTestId("test-1234567890abcdef1234567890abcdef")
    uuid = test_id.get_uuid()
    assert uuid.hex == "1234567890abcdef1234567890abcdef"


def test_random_id_get_uuid_without_prefix() -> None:
    """get_uuid should extract the UUID from an ID without a prefix."""
    no_prefix_id = NoPreFixId("1234567890abcdef1234567890abcdef")
    uuid = no_prefix_id.get_uuid()
    assert uuid.hex == "1234567890abcdef1234567890abcdef"


def test_random_id_without_prefix_generate_class_method() -> None:
    """generate should create a new ID without a prefix."""
    no_prefix_id = NoPreFixId.generate()
    assert isinstance(no_prefix_id, NoPreFixId)
    assert len(no_prefix_id) == 32
    # Verify it's valid hex
    int(no_prefix_id, 16)
