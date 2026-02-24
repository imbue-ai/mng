"""Tests for config pre-readers."""

from pathlib import Path

import pytest

from imbue.mng.config.pre_readers import read_default_host_dir

# =============================================================================
# Tests for read_default_host_dir
# =============================================================================


def test_read_default_host_dir_returns_env_var_when_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """read_default_host_dir should return MNG_HOST_DIR when set."""
    custom_dir = tmp_path / "custom-mng"
    monkeypatch.setenv("MNG_HOST_DIR", str(custom_dir))
    monkeypatch.setenv("MNG_ROOT_NAME", "mng-test-host-dir-env")

    assert read_default_host_dir() == custom_dir


def test_read_default_host_dir_falls_back_to_default_when_no_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """read_default_host_dir should return ~/.mng when no config files exist."""
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    monkeypatch.setenv("MNG_ROOT_NAME", "mng-test-host-dir-default")
    monkeypatch.setenv("HOME", str(tmp_path))

    result = read_default_host_dir()

    assert result == tmp_path / ".mng-test-host-dir-default"


def test_read_default_host_dir_reads_from_project_config(
    monkeypatch: pytest.MonkeyPatch,
    project_config_dir: Path,
    temp_git_repo_cwd: Path,
) -> None:
    """read_default_host_dir should read default_host_dir from project config."""
    # Unset MNG_HOST_DIR so the pre-reader falls through to config files
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    (project_config_dir / "settings.toml").write_text('default_host_dir = "/tmp/custom-host-dir"\n')

    result = read_default_host_dir()

    assert result == Path("/tmp/custom-host-dir")


def test_read_default_host_dir_local_overrides_project(
    monkeypatch: pytest.MonkeyPatch,
    project_config_dir: Path,
    temp_git_repo_cwd: Path,
) -> None:
    """read_default_host_dir should let local config override project config."""
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    (project_config_dir / "settings.toml").write_text('default_host_dir = "/tmp/project-dir"\n')
    (project_config_dir / "settings.local.toml").write_text('default_host_dir = "/tmp/local-dir"\n')

    result = read_default_host_dir()

    assert result == Path("/tmp/local-dir")


def test_read_default_host_dir_env_var_overrides_config(
    monkeypatch: pytest.MonkeyPatch,
    project_config_dir: Path,
    temp_git_repo_cwd: Path,
) -> None:
    """read_default_host_dir should let MNG_HOST_DIR env var override config files."""
    (project_config_dir / "settings.toml").write_text('default_host_dir = "/tmp/config-dir"\n')
    monkeypatch.setenv("MNG_HOST_DIR", "/tmp/env-dir")

    result = read_default_host_dir()

    assert result == Path("/tmp/env-dir")


def test_read_default_host_dir_expands_tilde(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """read_default_host_dir should expand ~ in the returned path."""
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    monkeypatch.setenv("MNG_ROOT_NAME", "mng-test-host-dir-tilde")
    monkeypatch.setenv("HOME", str(tmp_path))

    result = read_default_host_dir()

    # Should be an absolute path, not contain ~
    assert result.is_absolute()
    assert "~" not in str(result)
