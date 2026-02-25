"""Manage the mng install directory (~/.mng/install/).

The install directory is a self-managed uv project with its own pyproject.toml.
mng and all plugins are declared as dependencies. Plugin management modifies
the pyproject.toml via ``uv add`` / ``uv remove`` and lets uv sync the venv.

This replaces the previous approach of ``uv tool install``, which destroyed
plugins on upgrade because ``uv tool upgrade`` recreated the virtualenv.
"""

import os
import sys
from pathlib import Path
from typing import Any
from typing import Final

from imbue.imbue_common.pure import pure

_INSTALL_DIRNAME: Final[str] = "install"

_PYPROJECT_TEMPLATE: Final[str] = """\
[project]
name = "mng-install"
version = "0.0.0"
requires-python = ">=3.11"
dependencies = ["mng"]
"""


@pure
def get_install_dir() -> Path:
    """Return the install directory path based on MNG_ROOT_NAME.

    Defaults to ``~/.mng/install/``. When ``MNG_ROOT_NAME`` is set to e.g.
    ``foo``, returns ``~/.foo/install/``.
    """
    root_name = os.environ.get("MNG_ROOT_NAME", "mng")
    return Path.home() / f".{root_name}" / _INSTALL_DIRNAME


@pure
def get_install_venv_python(install_dir: Path) -> Path:
    """Return the Python interpreter path inside the install venv."""
    return install_dir / ".venv" / "bin" / "python"


def is_running_from_install_dir() -> bool:
    """Check whether the current process is running from the install venv.

    Returns True if ``sys.prefix`` matches the install directory's ``.venv``.
    Returns False when running from a development checkout (``uv run mng``)
    or any other venv.

    Uses ``sys.prefix`` (the venv root) rather than ``sys.executable``
    because the latter is a symlink that ``resolve()`` would follow out
    of the venv to the real Python binary.
    """
    install_dir = get_install_dir()
    venv_dir = (install_dir / ".venv").resolve()
    current_prefix = Path(sys.prefix).resolve()
    return current_prefix == venv_dir


def require_install_dir() -> Path:
    """Return the install directory, raising if plugin management is unavailable.

    Raises ``AbortError`` when running from a development checkout rather
    than the managed install.
    """
    # Import here to avoid circular dependency (output_helpers -> ... -> install_dir).
    from imbue.mng.cli.output_helpers import AbortError

    install_dir = get_install_dir()
    if not is_running_from_install_dir():
        raise AbortError(
            "Plugin management requires the installed version of mng. "
            f"Expected mng to be running from {install_dir / '.venv'}, "
            f"but sys.executable is {sys.executable}"
        )
    return install_dir


def ensure_install_dir(concurrency_group: Any) -> Path:
    """Create the install directory and pyproject.toml if absent, then sync.

    This is the bootstrap function: on first run it creates the project
    structure and runs ``uv sync`` to populate the venv. On subsequent
    runs it is a no-op (returns immediately when pyproject.toml exists).
    """
    install_dir = get_install_dir()
    pyproject_path = install_dir / "pyproject.toml"

    if pyproject_path.exists():
        return install_dir

    install_dir.mkdir(parents=True, exist_ok=True)
    pyproject_path.write_text(_PYPROJECT_TEMPLATE)

    concurrency_group.run_process_to_completion(("uv", "sync", "--project", str(install_dir)))

    return install_dir


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------


@pure
def build_uv_add_command(install_dir: Path, specifier: str) -> tuple[str, ...]:
    """Build a ``uv add`` command for a PyPI package specifier."""
    return ("uv", "add", "--project", str(install_dir), specifier)


def build_uv_add_command_for_path(install_dir: Path, local_path: str) -> tuple[str, ...]:
    """Build a ``uv add --editable`` command for a local path."""
    resolved = str(Path(local_path).expanduser().resolve())
    return ("uv", "add", "--project", str(install_dir), "--editable", resolved)


@pure
def build_uv_add_command_for_git(install_dir: Path, url: str) -> tuple[str, ...]:
    """Build a ``uv add`` command for a git URL.

    Prepends ``git+`` to the URL if it is not already present, as required
    by PEP 508 / uv.
    """
    git_url = url if url.startswith("git+") else f"git+{url}"
    return ("uv", "add", "--project", str(install_dir), git_url)


@pure
def build_uv_remove_command(install_dir: Path, package_name: str) -> tuple[str, ...]:
    """Build a ``uv remove`` command."""
    return ("uv", "remove", "--project", str(install_dir), package_name)
