"""Test fixtures for mng-schedule.

Uses shared plugin test fixtures from mng to avoid duplicating common
fixture code across plugin libraries.
"""

from pathlib import Path

import pluggy
import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())


@pytest.fixture()
def temp_mng_ctx(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> MngContext:
    """Create a MngContext for testing with default_host_dir pointing to tmp_path.

    Shared across mng-schedule tests that need a MngContext without a full
    provider setup.
    """
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(exist_ok=True)
    config = MngConfig(default_host_dir=tmp_path / ".mng")
    return MngContext(
        config=config,
        pm=plugin_manager,
        profile_dir=profile_dir,
        concurrency_group=ConcurrencyGroup(name="test"),
    )
