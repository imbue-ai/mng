from modal._grpc_client import UnaryStreamWrapper
from modal._grpc_client import UnaryUnaryWrapper

import imbue.resource_guards.resource_guards as resource_guards
from imbue.resource_guards_modal.guards import _cleanup_modal_guards
from imbue.resource_guards_modal.guards import _guarded_modal_unary_call
from imbue.resource_guards_modal.guards import _guarded_modal_unary_stream
from imbue.resource_guards_modal.guards import _install_modal_guards
from imbue.resource_guards_modal.guards import _modal_originals
from imbue.resource_guards_modal.guards import register_modal_guard


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


def test_create_sdk_resource_guards_populates_guarded_resources_modal(
    isolated_guard_state: None,
) -> None:
    register_modal_guard()
    resource_guards.create_sdk_resource_guards()

    assert "modal" in resource_guards._guarded_resources


def test_install_modal_guards_patches_grpc_wrappers(
    isolated_guard_state: None,
) -> None:
    """install records originals and patches the gRPC wrapper classes."""
    # Clean up any existing patches so we can install fresh
    _cleanup_modal_guards()

    _install_modal_guards()

    assert "unary_call" in _modal_originals
    assert "unary_stream" in _modal_originals
    assert UnaryUnaryWrapper.__call__ is _guarded_modal_unary_call
    assert UnaryStreamWrapper.unary_stream is _guarded_modal_unary_stream


def test_cleanup_modal_guards_restores_originals(
    isolated_guard_state: None,
) -> None:
    """cleanup restores the original gRPC wrapper methods after install."""
    _cleanup_modal_guards()

    original_call = UnaryUnaryWrapper.__call__
    original_stream = UnaryStreamWrapper.unary_stream

    _install_modal_guards()
    _cleanup_modal_guards()

    assert UnaryUnaryWrapper.__call__ is original_call
    assert UnaryStreamWrapper.unary_stream is original_stream
    assert len(_modal_originals) == 0


def test_cleanup_modal_guards_is_idempotent(
    isolated_guard_state: None,
) -> None:
    """Calling cleanup without install is safe (no-op)."""
    _cleanup_modal_guards()


def test_install_modal_guards_records_originals(
    isolated_guard_state: None,
) -> None:
    """install stores the original methods before patching."""
    _cleanup_modal_guards()

    original_call = UnaryUnaryWrapper.__call__
    original_stream = UnaryStreamWrapper.unary_stream

    _install_modal_guards()

    assert _modal_originals["unary_call"] is original_call
    assert _modal_originals["unary_stream"] is original_stream
    assert UnaryUnaryWrapper.__call__ is _guarded_modal_unary_call
    assert UnaryStreamWrapper.unary_stream is _guarded_modal_unary_stream

    _cleanup_modal_guards()
