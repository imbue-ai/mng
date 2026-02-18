import shutil

from imbue.mngr.errors import BinaryNotInstalledError


def check_binary_available(binary: str) -> bool:
    """Check if a binary is available on PATH."""
    return shutil.which(binary) is not None


def require_binary(binary: str, purpose: str, install_hint: str) -> None:
    """Raise BinaryNotInstalledError if a binary is not available on PATH."""
    if not check_binary_available(binary):
        raise BinaryNotInstalledError(binary, purpose, install_hint)
