import pytest

from imbue.mngr.errors import BinaryNotInstalledError
from imbue.mngr.utils.deps import check_binary_available
from imbue.mngr.utils.deps import require_binary


def test_check_binary_available_finds_existing_binary() -> None:
    """check_binary_available returns True for a binary known to exist."""
    assert check_binary_available("python3") is True


def test_check_binary_available_returns_false_for_missing_binary() -> None:
    """check_binary_available returns False for a nonexistent binary."""
    assert check_binary_available("definitely-not-a-real-binary-xyz") is False


def test_require_binary_passes_for_existing_binary() -> None:
    """require_binary does not raise for a binary that exists."""
    require_binary("python3", "testing", "Install python3")


def test_require_binary_raises_for_missing_binary() -> None:
    """require_binary raises BinaryNotInstalledError with correct fields."""
    with pytest.raises(BinaryNotInstalledError) as exc_info:
        require_binary("definitely-not-a-real-binary-xyz", "unit testing", "Try installing it.")

    err = exc_info.value
    assert "definitely-not-a-real-binary-xyz" in str(err)
    assert "unit testing" in str(err)
    assert err.user_help_text == "Try installing it."
