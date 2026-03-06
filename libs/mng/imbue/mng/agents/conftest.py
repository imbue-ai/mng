import os
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
def agent_event_env(tmp_path: Path) -> dict[str, str]:
    """Environment variables for running agent event shell commands.

    Sets MNG_AGENT_STATE_DIR (to tmp_path), MNG_AGENT_ID, and
    MNG_AGENT_NAME on top of the current process environment.
    """
    return {
        **os.environ,
        "MNG_AGENT_STATE_DIR": str(tmp_path),
        "MNG_AGENT_ID": "agent-test-fixture",
        "MNG_AGENT_NAME": "test-agent",
    }
