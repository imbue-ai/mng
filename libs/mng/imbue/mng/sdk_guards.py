from imbue.imbue_common.resource_guards import _enforce_sdk_guard
from imbue.imbue_common.resource_guards import register_sdk_guard

# Each guard pair manages its own originals dict so install/cleanup are symmetric.
_modal_originals: dict[str, object] = {}
_docker_originals: dict[str, object] = {}


def _install_modal_guards() -> None:
    """Monkeypatch Modal's gRPC wrapper classes to enforce resource guards.

    Patches UnaryUnaryWrapper.__call__ and UnaryStreamWrapper.unary_stream,
    which are the entry points for all Modal unary and streaming RPC calls.
    """
    try:
        from modal._grpc_client import UnaryStreamWrapper
        from modal._grpc_client import UnaryUnaryWrapper
    except ImportError:
        return

    original_call = UnaryUnaryWrapper.__call__
    original_stream = UnaryStreamWrapper.unary_stream
    _modal_originals["unary_call"] = original_call
    _modal_originals["unary_stream"] = original_stream

    # async is required here because the original methods are async
    async def guarded_unary_call(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _enforce_sdk_guard("modal")
        return await original_call(self, *args, **kwargs)

    async def guarded_unary_stream(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _enforce_sdk_guard("modal")
        async for response in original_stream(self, *args, **kwargs):
            yield response

    UnaryUnaryWrapper.__call__ = guarded_unary_call  # type: ignore[assignment]
    UnaryStreamWrapper.unary_stream = guarded_unary_stream  # type: ignore[assignment]


def _cleanup_modal_guards() -> None:
    if "unary_call" not in _modal_originals:
        return
    try:
        from modal._grpc_client import UnaryStreamWrapper
        from modal._grpc_client import UnaryUnaryWrapper
    except ImportError:
        return

    UnaryUnaryWrapper.__call__ = _modal_originals["unary_call"]  # type: ignore[assignment]
    UnaryStreamWrapper.unary_stream = _modal_originals["unary_stream"]  # type: ignore[assignment]
    _modal_originals.clear()


def _install_docker_guards() -> None:
    """Monkeypatch Docker's APIClient.send to enforce resource guards.

    APIClient inherits send from requests.Session. We shadow it on APIClient
    so that all Docker HTTP requests are guarded without affecting other
    requests.Session usage.
    """
    try:
        from docker.api.client import APIClient
    except ImportError:
        return

    # Capture whatever send() APIClient currently resolves to (via MRO).
    original_send = APIClient.send
    _docker_originals["send_existed"] = "send" in APIClient.__dict__
    if "send" in APIClient.__dict__:
        _docker_originals["send_original"] = APIClient.__dict__["send"]

    def guarded_send(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        _enforce_sdk_guard("docker")
        return original_send(self, *args, **kwargs)

    APIClient.send = guarded_send  # type: ignore[method-assign]


def _cleanup_docker_guards() -> None:
    if "send_existed" not in _docker_originals:
        return
    try:
        from docker.api.client import APIClient
    except ImportError:
        return

    if _docker_originals["send_existed"]:
        APIClient.send = _docker_originals["send_original"]  # type: ignore[method-assign]
    elif "send" in APIClient.__dict__:
        del APIClient.send  # type: ignore[misc]
    _docker_originals.clear()


def register_mng_sdk_guards() -> None:
    """Register Modal and Docker SDK guards with the resource guard infrastructure.

    Safe to call multiple times; register_sdk_guard deduplicates by name.
    Call this before register_conftest_hooks() in each conftest.py.
    """
    register_sdk_guard("modal", _install_modal_guards, _cleanup_modal_guards)
    register_sdk_guard("docker", _install_docker_guards, _cleanup_docker_guards)
