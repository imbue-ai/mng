import imbue.resource_guards.resource_guards as rg
from imbue.resource_guards_modal.guards import register_modal_guard


def test_register_modal_guard_adds_modal(
    isolated_guard_state: None,
) -> None:
    register_modal_guard()

    registered_names = [entry[0] for entry in rg._registered_sdk_guards]
    assert "modal" in registered_names


def test_register_modal_guard_deduplicates_on_repeated_calls(
    isolated_guard_state: None,
) -> None:
    register_modal_guard()
    register_modal_guard()

    registered_names = [entry[0] for entry in rg._registered_sdk_guards]
    assert registered_names.count("modal") == 1


def test_create_sdk_resource_guards_populates_guarded_resources_modal(
    isolated_guard_state: None,
) -> None:
    register_modal_guard()
    rg.create_sdk_resource_guards()

    assert "modal" in rg._guarded_resources
