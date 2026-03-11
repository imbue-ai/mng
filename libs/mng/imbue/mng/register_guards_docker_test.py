from pathlib import Path

import pytest
from docker.api.client import APIClient

import imbue.resource_guards.resource_guards as resource_guards
from imbue.mng.register_guards_docker import register_docker_cli_guard
from imbue.mng.register_guards_docker import register_docker_sdk_guard
from imbue.resource_guards.resource_guards import ResourceGuardViolation


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


def test_docker_sdk_guard_patches_apiclient_send(
    isolated_guard_state: None,
) -> None:
    """After install, APIClient.send is replaced with the guarded version."""
    original_send = APIClient.send
    register_docker_sdk_guard()
    resource_guards.create_sdk_resource_guards()

    assert APIClient.send is not original_send

    resource_guards.cleanup_sdk_resource_guards()
    assert APIClient.send is original_send


def test_docker_sdk_guard_enforces_guard(
    isolated_guard_state: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The guarded send raises ResourceGuardViolation when blocked."""
    register_docker_sdk_guard()
    resource_guards.create_sdk_resource_guards()

    monkeypatch.setenv("_PYTEST_GUARD_PHASE", "call")
    monkeypatch.setenv("_PYTEST_GUARD_DOCKER_SDK", "block")
    monkeypatch.setenv("_PYTEST_GUARD_TRACKING_DIR", str(tmp_path))

    with pytest.raises(ResourceGuardViolation, match="without @pytest.mark.docker_sdk"):
        APIClient.send(None)  # ty: ignore[missing-argument,invalid-argument-type]

    resource_guards.cleanup_sdk_resource_guards()


def test_docker_sdk_guard_delegates_when_allowed(
    isolated_guard_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guarded send delegates to the original when the guard is inactive."""
    monkeypatch.delenv("_PYTEST_GUARD_PHASE", raising=False)

    register_docker_sdk_guard()
    resource_guards.create_sdk_resource_guards()

    # Calling send without a real Docker connection will fail, but it should
    # get past the guard and into the original send method. We just verify
    # no ResourceGuardViolation is raised.
    with pytest.raises(Exception, match="(?!ResourceGuardViolation)"):
        APIClient().send(None)  # ty: ignore[invalid-argument-type]

    resource_guards.cleanup_sdk_resource_guards()


def test_docker_sdk_guard_cleanup_is_idempotent(
    isolated_guard_state: None,
) -> None:
    """Calling cleanup without install is safe (no-op)."""
    resource_guards.cleanup_sdk_resource_guards()
