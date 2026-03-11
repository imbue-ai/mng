import asyncio
from pathlib import Path

import pytest
from modal._grpc_client import UnaryStreamWrapper
from modal._grpc_client import UnaryUnaryWrapper

import imbue.resource_guards.resource_guards as resource_guards
from imbue.mng.register_guards_modal import register_modal_guard
from imbue.resource_guards.resource_guards import ResourceGuardViolation


def test_register_modal_guard_adds_modal(
    isolated_guard_state: None,
) -> None:
    register_modal_guard()

    registered_names = [entry[0] for entry in resource_guards._registered_sdk_guards]
    assert "modal" in registered_names


def test_register_modal_guard_deduplicates_on_repeated_calls(
    isolated_guard_state: None,
) -> None:
    register_modal_guard()
    register_modal_guard()

    registered_names = [entry[0] for entry in resource_guards._registered_sdk_guards]
    assert registered_names.count("modal") == 1


def test_modal_guard_patches_grpc_wrappers(
    isolated_guard_state: None,
) -> None:
    """After install, the gRPC wrapper classes are patched."""
    original_call = UnaryUnaryWrapper.__call__
    original_stream = UnaryStreamWrapper.unary_stream

    register_modal_guard()
    resource_guards.create_sdk_resource_guards()

    assert UnaryUnaryWrapper.__call__ is not original_call
    assert UnaryStreamWrapper.unary_stream is not original_stream

    resource_guards.cleanup_sdk_resource_guards()
    assert UnaryUnaryWrapper.__call__ is original_call
    assert UnaryStreamWrapper.unary_stream is original_stream


def test_modal_guard_enforces_on_unary_call(
    isolated_guard_state: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The guarded unary call raises ResourceGuardViolation when blocked."""
    register_modal_guard()
    resource_guards.create_sdk_resource_guards()

    monkeypatch.setenv("_PYTEST_GUARD_PHASE", "call")
    monkeypatch.setenv("_PYTEST_GUARD_MODAL", "block")
    monkeypatch.setenv("_PYTEST_GUARD_TRACKING_DIR", str(tmp_path))

    with pytest.raises(ResourceGuardViolation, match="without @pytest.mark.modal"):
        asyncio.get_event_loop().run_until_complete(
            UnaryUnaryWrapper.__call__(None)  # ty: ignore[no-matching-overload]
        )

    resource_guards.cleanup_sdk_resource_guards()


def test_modal_guard_delegates_unary_call(
    isolated_guard_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guarded unary call delegates to the original when the guard is inactive."""
    monkeypatch.delenv("_PYTEST_GUARD_PHASE", raising=False)

    sentinel = object()

    async def fake_call(self, *args, **kwargs):
        return sentinel

    # Set the fake before installing so the guard captures it as the "original"
    UnaryUnaryWrapper.__call__ = fake_call  # ty: ignore[invalid-assignment]
    register_modal_guard()
    resource_guards.create_sdk_resource_guards()

    result = asyncio.get_event_loop().run_until_complete(
        UnaryUnaryWrapper.__call__(None)  # ty: ignore[no-matching-overload]
    )
    assert result is sentinel

    resource_guards.cleanup_sdk_resource_guards()


def test_modal_guard_delegates_unary_stream(
    isolated_guard_state: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guarded unary stream yields from the original when the guard is inactive."""
    monkeypatch.delenv("_PYTEST_GUARD_PHASE", raising=False)

    async def fake_stream(self, *args, **kwargs):
        yield "a"
        yield "b"

    # Set the fake before installing so the guard captures it as the "original"
    UnaryStreamWrapper.unary_stream = fake_stream  # ty: ignore[invalid-assignment]
    register_modal_guard()
    resource_guards.create_sdk_resource_guards()

    async def collect():
        results = []
        async for item in UnaryStreamWrapper.unary_stream(None):  # ty: ignore[missing-argument,invalid-argument-type]
            results.append(item)
        return results

    results = asyncio.get_event_loop().run_until_complete(collect())
    assert results == ["a", "b"]

    resource_guards.cleanup_sdk_resource_guards()


def test_modal_guard_cleanup_is_idempotent(
    isolated_guard_state: None,
) -> None:
    """Calling cleanup without install is safe (no-op)."""
    resource_guards.cleanup_sdk_resource_guards()
