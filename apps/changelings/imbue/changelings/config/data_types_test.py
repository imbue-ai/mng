from pathlib import Path

import pytest

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.config.data_types import get_default_data_dir
from imbue.changelings.config.data_types import get_default_mng_host_dir


def test_changeling_paths_auth_dir(tmp_path: Path) -> None:
    paths = ChangelingPaths(data_dir=tmp_path)

    assert paths.auth_dir == tmp_path / "auth"


def test_get_default_data_dir_returns_home_based_path() -> None:
    data_dir = get_default_data_dir()

    assert data_dir.name == ".changelings"
    assert data_dir.parent == Path.home()


def test_get_default_mng_host_dir_returns_home_based_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    host_dir = get_default_mng_host_dir()

    assert host_dir.name == ".mng"
    assert host_dir.parent == Path.home()


def test_get_default_mng_host_dir_respects_env_var(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MNG_HOST_DIR", str(tmp_path / "custom-mng"))
    host_dir = get_default_mng_host_dir()

    assert host_dir == tmp_path / "custom-mng"
