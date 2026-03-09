from typing import Any

from modal._grpc_client import UnaryStreamWrapper
from modal._grpc_client import UnaryUnaryWrapper

from imbue.resource_guards.resource_guards import enforce_sdk_guard
from imbue.resource_guards.resource_guards import register_sdk_guard

# Stores original methods so they can be restored by cleanup.
# Typed as Any because the values are method references with heterogeneous signatures.
_modal_originals: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Module-level guard functions (looked up from originals dicts at call time)
# ---------------------------------------------------------------------------


# async is required here because the original methods are async
async def _guarded_modal_unary_call(self, *args, **kwargs):
    enforce_sdk_guard("modal")
    original = _modal_originals["unary_call"]
    return await original(self, *args, **kwargs)


async def _guarded_modal_unary_stream(self, *args, **kwargs):
    enforce_sdk_guard("modal")
    original = _modal_originals["unary_stream"]
    async for response in original(self, *args, **kwargs):
        yield response


# ---------------------------------------------------------------------------
# Install / cleanup
# ---------------------------------------------------------------------------


def _install_modal_guards() -> None:
    """Monkeypatch Modal's gRPC wrapper classes to enforce resource guards.

    Patches UnaryUnaryWrapper.__call__ and UnaryStreamWrapper.unary_stream,
    which are the entry points for all Modal unary and streaming RPC calls.
    """
    _modal_originals["unary_call"] = UnaryUnaryWrapper.__call__
    _modal_originals["unary_stream"] = UnaryStreamWrapper.unary_stream

    UnaryUnaryWrapper.__call__ = _guarded_modal_unary_call  # ty: ignore[invalid-assignment]
    UnaryStreamWrapper.unary_stream = _guarded_modal_unary_stream  # ty: ignore[invalid-assignment]


def _cleanup_modal_guards() -> None:
    if "unary_call" not in _modal_originals:
        return

    UnaryUnaryWrapper.__call__ = _modal_originals["unary_call"]
    UnaryStreamWrapper.unary_stream = _modal_originals["unary_stream"]
    _modal_originals.clear()


# ---------------------------------------------------------------------------
# Registration (called from each project's conftest.py)
# ---------------------------------------------------------------------------


def register_modal_guard() -> None:
    """Register the Modal SDK guard. Safe to call multiple times."""
    register_sdk_guard("modal", _install_modal_guards, _cleanup_modal_guards)
