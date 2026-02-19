from pathlib import Path

import pytest

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.primitives import ChangelingName


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate config operations to a temporary home directory."""
    monkeypatch.setenv("HOME", str(tmp_path))


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
