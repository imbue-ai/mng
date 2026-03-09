import pytest

from imbue.resource_guards.testing import isolate_guard_state


@pytest.fixture()
def isolated_guard_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate resource guard module state for guard tests."""
    isolate_guard_state(monkeypatch)
