import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Generator

import pluggy
import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.utils.testing import make_mng_ctx


@pytest.fixture
def interactive_mng_ctx(
    temp_config: MngConfig, temp_profile_dir: Path, plugin_manager: pluggy.PluginManager
) -> Generator[MngContext, None, None]:
    """Create an interactive MngContext with a temporary host directory.

    Use this fixture when testing code paths that require is_interactive=True.
    """
    cg = ConcurrencyGroup(name="test-interactive")
    with cg:
        yield make_mng_ctx(temp_config, plugin_manager, temp_profile_dir, is_interactive=True, concurrency_group=cg)


@pytest.fixture
def run_event_command(tmp_path: Path) -> Callable[[str], subprocess.CompletedProcess[str]]:
    """Return a callable that runs a shell command with standard agent env vars.

    Sets MNG_AGENT_STATE_DIR, MNG_AGENT_ID, and MNG_AGENT_NAME in the
    subprocess environment and asserts that the command succeeds.
    """
    env = {
        **os.environ,
        "MNG_AGENT_STATE_DIR": str(tmp_path),
        "MNG_AGENT_ID": "agent-test-fixture",
        "MNG_AGENT_NAME": "test-agent",
    }

    def _run(command: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(["bash", "-c", command], env=env, capture_output=True, text=True)
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        return result

    return _run
