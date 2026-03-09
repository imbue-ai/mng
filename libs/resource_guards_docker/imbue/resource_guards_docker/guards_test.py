import imbue.resource_guards.resource_guards as rg
from imbue.resource_guards_docker.guards import register_docker_cli_guard
from imbue.resource_guards_docker.guards import register_docker_sdk_guard


def test_register_docker_sdk_guard_adds_docker_sdk(
    isolated_guard_state: None,
) -> None:
    register_docker_sdk_guard()

    registered_names = [entry[0] for entry in rg._registered_sdk_guards]
    assert "docker_sdk" in registered_names


def test_register_docker_cli_guard_adds_docker_binary(
    isolated_guard_state: None,
) -> None:
    register_docker_cli_guard()

    assert "docker" in rg._guarded_resources


def test_create_sdk_resource_guards_populates_guarded_resources_docker(
    isolated_guard_state: None,
) -> None:
    register_docker_sdk_guard()
    rg.create_sdk_resource_guards()

    assert "docker_sdk" in rg._guarded_resources
