from typing import Any

from docker.api.client import APIClient

from imbue.resource_guards.resource_guards import enforce_sdk_guard
from imbue.resource_guards.resource_guards import register_resource_guard
from imbue.resource_guards.resource_guards import register_sdk_guard

# Stores original methods so they can be restored by cleanup.
# Typed as Any because the values are method references with heterogeneous signatures.
_docker_originals: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Module-level guard functions (looked up from originals dicts at call time)
# ---------------------------------------------------------------------------


def _guarded_docker_send(self, *args, **kwargs):
    enforce_sdk_guard("docker_sdk")
    original = _docker_originals["send_original_resolved"]
    return original(self, *args, **kwargs)


# ---------------------------------------------------------------------------
# Install / cleanup
# ---------------------------------------------------------------------------


def _install_docker_sdk_guards() -> None:
    """Monkeypatch Docker's APIClient.send to enforce resource guards.

    APIClient inherits send from requests.Session. We shadow it on APIClient
    so that all Docker HTTP requests are guarded without affecting other
    requests.Session usage.
    """
    _docker_originals["send_original_resolved"] = APIClient.send
    _docker_originals["send_existed"] = "send" in APIClient.__dict__
    if "send" in APIClient.__dict__:
        _docker_originals["send_original"] = APIClient.__dict__["send"]

    APIClient.send = _guarded_docker_send  # ty: ignore[invalid-assignment]


def _cleanup_docker_sdk_guards() -> None:
    if "send_existed" not in _docker_originals:
        return

    if _docker_originals["send_existed"]:
        APIClient.send = _docker_originals["send_original"]
    elif "send" in APIClient.__dict__:
        # No send was defined directly on APIClient before we patched it;
        # remove our shadow so MRO resolution goes back to the parent class.
        del APIClient.send
    else:
        # Our shadow was already removed (e.g. by another cleanup path).
        pass
    _docker_originals.clear()


# ---------------------------------------------------------------------------
# Registration (called from each project's conftest.py)
# ---------------------------------------------------------------------------


def register_docker_cli_guard() -> None:
    """Register the Docker CLI binary guard. Safe to call multiple times.

    Uses a PATH wrapper to intercept docker CLI subprocess calls, including
    from child processes launched by mng create.
    """
    register_resource_guard("docker")


def register_docker_sdk_guard() -> None:
    """Register the Docker SDK guard. Safe to call multiple times.

    Monkeypatches APIClient.send to intercept in-process Docker SDK HTTP calls.
    """
    register_sdk_guard("docker_sdk", _install_docker_sdk_guards, _cleanup_docker_sdk_guards)
