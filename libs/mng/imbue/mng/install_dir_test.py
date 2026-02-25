from pathlib import Path

import pytest

from imbue.mng.cli.output_helpers import AbortError
from imbue.mng.install_dir import _PYPROJECT_TEMPLATE
from imbue.mng.install_dir import build_uv_add_command
from imbue.mng.install_dir import build_uv_add_command_for_git
from imbue.mng.install_dir import build_uv_add_command_for_path
from imbue.mng.install_dir import build_uv_remove_command
from imbue.mng.install_dir import ensure_install_dir
from imbue.mng.install_dir import get_install_dir
from imbue.mng.install_dir import get_install_venv_python
from imbue.mng.install_dir import is_running_from_install_dir
from imbue.mng.install_dir import require_install_dir

# =============================================================================
# Tests for get_install_dir
# =============================================================================


def test_get_install_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_install_dir should return ~/.mng/install/ by default."""
    monkeypatch.setenv("MNG_ROOT_NAME", "mng")
    result = get_install_dir()
    assert result == Path.home() / ".mng" / "install"


def test_get_install_dir_custom_root_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_install_dir should respect MNG_ROOT_NAME."""
    monkeypatch.setenv("MNG_ROOT_NAME", "foo")
    result = get_install_dir()
    assert result == Path.home() / ".foo" / "install"


# =============================================================================
# Tests for get_install_venv_python
# =============================================================================


def test_get_install_venv_python() -> None:
    """get_install_venv_python should return .venv/bin/python inside install dir."""
    install_dir = Path("/tmp/test-install")
    result = get_install_venv_python(install_dir)
    assert result == Path("/tmp/test-install/.venv/bin/python")


# =============================================================================
# Tests for is_running_from_install_dir
# =============================================================================


def test_is_running_from_install_dir_returns_false_in_dev_mode() -> None:
    """is_running_from_install_dir should return False when running from dev venv."""
    # In the test environment, sys.executable is the workspace venv python,
    # not the install dir's python.
    assert is_running_from_install_dir() is False


# =============================================================================
# Tests for require_install_dir
# =============================================================================


def test_require_install_dir_raises_in_dev_mode() -> None:
    """require_install_dir should raise AbortError when not running from install dir."""
    with pytest.raises(AbortError, match="Plugin management requires the installed version"):
        require_install_dir()


# =============================================================================
# Tests for ensure_install_dir
# =============================================================================


def test_ensure_install_dir_creates_pyproject_when_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ensure_install_dir should create pyproject.toml when the install dir is empty."""
    install_dir = tmp_path / ".mng" / "install"
    monkeypatch.setenv("MNG_ROOT_NAME", "mng")
    monkeypatch.setenv("HOME", str(tmp_path))

    uv_sync_called = False

    class FakeConcurrencyGroup:
        def run_process_to_completion(self, command: tuple[str, ...]) -> None:
            nonlocal uv_sync_called
            assert command == ("uv", "sync", "--project", str(install_dir))
            uv_sync_called = True

    ensure_install_dir(FakeConcurrencyGroup())

    assert (install_dir / "pyproject.toml").exists()
    assert (install_dir / "pyproject.toml").read_text() == _PYPROJECT_TEMPLATE
    assert uv_sync_called


def test_ensure_install_dir_is_noop_when_pyproject_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ensure_install_dir should not run uv sync when pyproject.toml already exists."""
    install_dir = tmp_path / ".mng" / "install"
    install_dir.mkdir(parents=True)
    (install_dir / "pyproject.toml").write_text(_PYPROJECT_TEMPLATE)
    monkeypatch.setenv("MNG_ROOT_NAME", "mng")
    monkeypatch.setenv("HOME", str(tmp_path))

    class FakeConcurrencyGroup:
        def run_process_to_completion(self, command: tuple[str, ...]) -> None:
            raise AssertionError("uv sync should not be called")

    result = ensure_install_dir(FakeConcurrencyGroup())
    assert result == install_dir


# =============================================================================
# Tests for build_uv_add_command
# =============================================================================


def test_build_uv_add_command_pypi() -> None:
    """build_uv_add_command should produce a uv add command for PyPI packages."""
    install_dir = Path("/tmp/install")
    cmd = build_uv_add_command(install_dir, "mng-opencode>=1.0")
    assert cmd == ("uv", "add", "--project", "/tmp/install", "mng-opencode>=1.0")


def test_build_uv_add_command_for_path() -> None:
    """build_uv_add_command_for_path should use --editable flag."""
    install_dir = Path("/tmp/install")
    cmd = build_uv_add_command_for_path(install_dir, "./my-plugin")
    assert cmd[0:5] == ("uv", "add", "--project", "/tmp/install", "--editable")
    # The path should be resolved to an absolute path
    assert Path(cmd[5]).is_absolute()


def test_build_uv_add_command_for_git_prepends_git_plus() -> None:
    """build_uv_add_command_for_git should prepend git+ to https URLs."""
    install_dir = Path("/tmp/install")
    cmd = build_uv_add_command_for_git(install_dir, "https://github.com/user/repo.git")
    assert cmd == ("uv", "add", "--project", "/tmp/install", "git+https://github.com/user/repo.git")


def test_build_uv_add_command_for_git_does_not_double_prefix() -> None:
    """build_uv_add_command_for_git should not double the git+ prefix."""
    install_dir = Path("/tmp/install")
    cmd = build_uv_add_command_for_git(install_dir, "git+https://github.com/user/repo.git")
    assert cmd == ("uv", "add", "--project", "/tmp/install", "git+https://github.com/user/repo.git")


# =============================================================================
# Tests for build_uv_remove_command
# =============================================================================


def test_build_uv_remove_command() -> None:
    """build_uv_remove_command should produce a uv remove command."""
    install_dir = Path("/tmp/install")
    cmd = build_uv_remove_command(install_dir, "mng-opencode")
    assert cmd == ("uv", "remove", "--project", "/tmp/install", "mng-opencode")
