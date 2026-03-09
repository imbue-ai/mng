import pytest
from docker.api.client import APIClient

import imbue.resource_guards.resource_guards as resource_guards
from imbue.resource_guards_docker.guards import _cleanup_docker_sdk_guards
from imbue.resource_guards_docker.guards import _docker_originals
from imbue.resource_guards_docker.guards import _guarded_docker_send
from imbue.resource_guards_docker.guards import _install_docker_sdk_guards
from imbue.resource_guards_docker.guards import register_docker_cli_guard
from imbue.resource_guards_docker.guards import register_docker_sdk_guard


def test_register_docker_sdk_guard_adds_docker_sdk(
    isolated_guard_state: None,
) -> None:
    register_docker_sdk_guard()

    registered_names = [entry[0] for entry in resource_guards._registered_sdk_guards]
    assert "docker_sdk" in registered_names


def test_register_docker_cli_guard_adds_docker_binary(
    isolated_guard_state: None,
) -> None:
    register_docker_cli_guard()

    assert "docker" in resource_guards._guarded_resources


def test_create_sdk_resource_guards_populates_guarded_resources_docker(
    isolated_guard_state: None,
) -> None:
    register_docker_sdk_guard()
    resource_guards.create_sdk_resource_guards()

    assert "docker_sdk" in resource_guards._guarded_resources


def test_install_docker_sdk_guards_patches_apiclient_send(
    isolated_guard_state: None,
) -> None:
    """install records the original send method and patches APIClient.send."""
    # Clean up any existing patches so we can install fresh
    _cleanup_docker_sdk_guards()

    _install_docker_sdk_guards()

    assert "send_original_resolved" in _docker_originals
    assert "send_existed" in _docker_originals
    assert APIClient.send is _guarded_docker_send


def test_cleanup_docker_sdk_guards_restores_original(
    isolated_guard_state: None,
) -> None:
    """cleanup restores the original APIClient.send after install."""
    _cleanup_docker_sdk_guards()

    original_send = APIClient.send
    _install_docker_sdk_guards()
    _cleanup_docker_sdk_guards()

    assert APIClient.send is original_send
    assert len(_docker_originals) == 0


def test_cleanup_docker_sdk_guards_is_idempotent(
    isolated_guard_state: None,
) -> None:
    """Calling cleanup without install is safe (no-op)."""
    _cleanup_docker_sdk_guards()


def test_guarded_docker_send_delegates_to_original(
    isolated_guard_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guarded send function calls enforce_sdk_guard and delegates."""
    monkeypatch.delenv("_PYTEST_GUARD_PHASE", raising=False)

    sentinel = object()
    _docker_originals["send_original_resolved"] = lambda self, *a, **kw: sentinel

    result = _guarded_docker_send(None)

    assert result is sentinel
    _docker_originals.clear()
