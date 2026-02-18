import pytest

from imbue.mngr.errors import BinaryNotInstalledError
from imbue.mngr.utils.deps import SystemDependency


def test_system_dependency_is_available_for_existing_binary() -> None:
    """is_available returns True for a binary known to exist."""
    dep = SystemDependency(binary="python3", purpose="testing", install_hint="Install python3")
    assert dep.is_available() is True


def test_system_dependency_is_available_for_missing_binary() -> None:
    """is_available returns False for a nonexistent binary."""
    dep = SystemDependency(binary="definitely-not-a-real-binary-xyz", purpose="testing", install_hint="N/A")
    assert dep.is_available() is False


def test_system_dependency_require_passes_for_existing_binary() -> None:
    """require does not raise for a binary that exists."""
    dep = SystemDependency(binary="python3", purpose="testing", install_hint="Install python3")
    dep.require()


def test_system_dependency_require_raises_for_missing_binary() -> None:
    """require raises BinaryNotInstalledError with correct fields."""
    dep = SystemDependency(
        binary="definitely-not-a-real-binary-xyz",
        purpose="unit testing",
        install_hint="Try installing it.",
    )
    with pytest.raises(BinaryNotInstalledError) as exc_info:
        dep.require()

    err = exc_info.value
    assert "definitely-not-a-real-binary-xyz" in str(err)
    assert "unit testing" in str(err)
    assert err.user_help_text == "Try installing it."
