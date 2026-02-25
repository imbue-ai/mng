from pathlib import Path

import pytest

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.primitives import ChangelingName
from imbue.mng.utils.testing import isolate_home

_REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate config operations to a temporary home directory."""
    isolate_home(tmp_path, monkeypatch)


@pytest.fixture
def imbue_repo_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Change working directory to the imbue repo root.

    Use this for tests that need to run git commands against the real repository
    (e.g. finding the repo root, getting commit hashes, or getting remote URLs).
    """
    monkeypatch.chdir(_REPO_ROOT)
    return _REPO_ROOT


def make_test_changeling(
    name: str = "test-changeling",
    agent_type: str = "code-guardian",
    branch: str = "main",
    initial_message: str = DEFAULT_INITIAL_MESSAGE,
    extra_mng_args: str = "",
    env_vars: dict[str, str] | None = None,
    secrets: tuple[str, ...] | None = None,
    mng_options: dict[str, str] | None = None,
    mng_profile: str | None = None,
) -> ChangelingDefinition:
    """Create a ChangelingDefinition for testing."""
    kwargs: dict = {
        "name": ChangelingName(name),
        "agent_type": agent_type,
        "branch": branch,
        "initial_message": initial_message,
        "extra_mng_args": extra_mng_args,
        "env_vars": env_vars or {},
        "mng_options": mng_options or {},
    }
    if secrets is not None:
        kwargs["secrets"] = secrets
    if mng_profile is not None:
        kwargs["mng_profile"] = mng_profile
    return ChangelingDefinition(**kwargs)
