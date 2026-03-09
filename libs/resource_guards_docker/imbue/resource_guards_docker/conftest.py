import pytest

import imbue.resource_guards.resource_guards as rg


@pytest.fixture()
def isolated_guard_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate resource guard module state for guard tests."""
    monkeypatch.setattr(rg, "_guard_wrapper_dir", None)
    monkeypatch.setattr(rg, "_owns_guard_wrapper_dir", False)
    monkeypatch.setattr(rg, "_session_env_patcher", None)
    monkeypatch.setattr(rg, "_guarded_resources", [])
    monkeypatch.setattr(rg, "_registered_sdk_guards", [])
