"""Test fixtures for mng-tutor.

Uses shared plugin test fixtures from mng for common setup (plugin manager,
environment isolation, git repos, etc.) and defines tutor-specific fixtures below.
"""

import os
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pluggy
import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import PROFILES_DIRNAME
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.utils.plugin_testing import register_plugin_test_fixtures

register_plugin_test_fixtures(globals())


@pytest.fixture
def temp_config(temp_host_dir: Path) -> MngConfig:
    """Create a MngConfig with a temporary host directory."""
    mng_test_prefix = os.environ.get("MNG_PREFIX", "mng-test-")
    return MngConfig(default_host_dir=temp_host_dir, prefix=mng_test_prefix, is_error_reporting_enabled=False)


@pytest.fixture
def temp_profile_dir(temp_host_dir: Path) -> Path:
    """Create a temporary profile directory."""
    profile_dir = temp_host_dir / PROFILES_DIRNAME / uuid4().hex
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


@pytest.fixture
def temp_mng_ctx(
    temp_config: MngConfig, temp_profile_dir: Path, plugin_manager: pluggy.PluginManager
) -> Generator[MngContext, None, None]:
    """Create a MngContext with a temporary host directory."""
    with ConcurrencyGroup(name="test") as cg:
        yield MngContext(
            config=temp_config,
            pm=plugin_manager,
            profile_dir=temp_profile_dir,
            is_interactive=False,
            is_auto_approve=False,
            concurrency_group=cg,
        )


@pytest.fixture
def local_provider(temp_host_dir: Path, temp_mng_ctx: MngContext) -> LocalProviderInstance:
    """Create a LocalProviderInstance with a temporary host directory."""
    return LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mng_ctx=temp_mng_ctx,
    )
