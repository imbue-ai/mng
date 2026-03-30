"""Tests that mngr works correctly when installed without optional plugin packages.

These tests install mngr into an isolated venv that contains only the core
package and its direct dependencies -- no plugin packages like mngr_modal,
mngr_claude, etc. This catches regressions where the core CLI accidentally
assumes an optional plugin is always available (e.g. eagerly importing modal).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from imbue.mngr.utils.testing import init_git_repo


def _make_subprocess_env(venv_dir: Path, host_dir: Path, root_name: str) -> dict[str, str]:
    """Build an environment dict for running mngr in the isolated venv."""
    return {
        "PATH": f"{venv_dir / 'bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(host_dir.parent),
        "MNGR_HOST_DIR": str(host_dir),
        "MNGR_ROOT_NAME": root_name,
    }


def _run_mngr(
    venv_dir: Path,
    args: list[str],
    env: dict[str, str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run the venv's mngr binary with the given arguments."""
    mngr_bin = str(venv_dir / "bin" / "mngr")
    return subprocess.run(
        [mngr_bin, *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=30,
    )


@pytest.fixture
def minimal_install_env(
    isolated_mngr_venv: Path,
    temp_host_dir: Path,
    mngr_test_root_name: str,
    tmp_path: Path,
) -> tuple[Path, dict[str, str], Path]:
    """Provide an isolated venv, subprocess env, and git repo for install tests.

    The venv has only the core mngr package -- no plugin packages. The env dict
    is configured so mngr uses isolated directories and won't load project config.
    """
    env = _make_subprocess_env(isolated_mngr_venv, temp_host_dir, mngr_test_root_name)

    # Create a git repo for mngr to run in (it expects to be in one)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    init_git_repo(repo_dir)

    return isolated_mngr_venv, env, repo_dir


@pytest.mark.release
@pytest.mark.timeout(60)
def test_help_without_plugins(
    minimal_install_env: tuple[Path, dict[str, str], Path],
) -> None:
    """mngr --help works in a clean install without any plugin packages."""
    venv_dir, env, repo_dir = minimal_install_env

    result = _run_mngr(venv_dir, ["--help"], env, repo_dir)

    assert result.returncode == 0, (
        f"mngr --help failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Usage" in result.stdout
    assert "create" in result.stdout
    assert "list" in result.stdout


@pytest.mark.release
@pytest.mark.timeout(60)
def test_create_help_without_plugins(
    minimal_install_env: tuple[Path, dict[str, str], Path],
) -> None:
    """mngr create --help works without plugin packages."""
    venv_dir, env, repo_dir = minimal_install_env

    result = _run_mngr(venv_dir, ["create", "--help"], env, repo_dir)

    assert result.returncode == 0, (
        f"mngr create --help failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "--command" in result.stdout
    assert "--no-connect" in result.stdout


@pytest.mark.release
@pytest.mark.timeout(60)
def test_list_without_plugins(
    minimal_install_env: tuple[Path, dict[str, str], Path],
) -> None:
    """mngr list works in a clean install and returns no agents."""
    venv_dir, env, repo_dir = minimal_install_env

    result = _run_mngr(venv_dir, ["list"], env, repo_dir)

    assert result.returncode == 0, (
        f"mngr list failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "No agents found" in result.stdout


@pytest.mark.release
@pytest.mark.timeout(60)
def test_list_json_without_plugins(
    minimal_install_env: tuple[Path, dict[str, str], Path],
) -> None:
    """mngr list --format json works and returns valid JSON with empty agents."""
    venv_dir, env, repo_dir = minimal_install_env

    result = _run_mngr(venv_dir, ["list", "--format", "json"], env, repo_dir)

    assert result.returncode == 0, (
        f"mngr list --format json failed (exit {result.returncode}):\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    parsed = json.loads(result.stdout)
    assert parsed["agents"] == []


@pytest.mark.release
@pytest.mark.timeout(60)
def test_no_eager_plugin_imports(
    minimal_install_env: tuple[Path, dict[str, str], Path],
) -> None:
    """Importing mngr's main module does not eagerly import optional plugin modules.

    This is a defense against accidental top-level imports that would cause
    ImportError for users who haven't installed optional plugins like modal.
    """
    venv_dir, env, repo_dir = minimal_install_env

    python_bin = str(venv_dir / "bin" / "python")
    check_script = (
        "import imbue.mngr.main; import sys; "
        "optional = ['modal', 'imbue.mngr_modal', 'imbue.mngr_claude']; "
        "imported = [m for m in optional if m in sys.modules]; "
        "assert not imported, f'Unexpected eager imports: {imported}'"
    )
    result = subprocess.run(
        [python_bin, "-c", check_script],
        capture_output=True,
        text=True,
        cwd=repo_dir,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"Optional plugin modules were eagerly imported:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
