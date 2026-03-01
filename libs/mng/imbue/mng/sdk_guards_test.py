import pytest

import imbue.imbue_common.resource_guards as rg
from imbue.mng.sdk_guards import register_mng_sdk_guards


@pytest.fixture()
def isolated_guard_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate resource guard module state for sdk_guards tests."""
    monkeypatch.setattr(rg, "_guard_wrapper_dir", None)
    monkeypatch.setattr(rg, "_owns_guard_wrapper_dir", False)
    monkeypatch.setattr(rg, "_session_env_patcher", None)
    monkeypatch.setattr(rg, "_guarded_resources", [])
    monkeypatch.setattr(rg, "_registered_sdk_guards", [])


def test_register_mng_sdk_guards_adds_modal_and_docker(
    isolated_guard_state: None,
) -> None:
    register_mng_sdk_guards()

    registered_names = [entry[0] for entry in rg._registered_sdk_guards]
    assert "modal" in registered_names
    assert "docker" in registered_names


def test_register_mng_sdk_guards_deduplicates_on_repeated_calls(
    isolated_guard_state: None,
) -> None:
    register_mng_sdk_guards()
    register_mng_sdk_guards()

    registered_names = [entry[0] for entry in rg._registered_sdk_guards]
    assert registered_names.count("modal") == 1
    assert registered_names.count("docker") == 1


def test_create_sdk_resource_guards_populates_guarded_resources(
    isolated_guard_state: None,
) -> None:
    register_mng_sdk_guards()
    rg.create_sdk_resource_guards()

    assert "modal" in rg._guarded_resources
    assert "docker" in rg._guarded_resources
