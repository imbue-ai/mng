"""Unit tests for the mng-schedule plugin registration."""

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import click

from imbue.mng.config.data_types import MngContext
from imbue.mng_schedule.plugin import get_files_for_deploy
from imbue.mng_schedule.plugin import register_cli_commands


def test_register_cli_commands_returns_schedule_command() -> None:
    """Verify that register_cli_commands returns the schedule command."""
    result = register_cli_commands()

    assert result is not None
    assert isinstance(result, Sequence)
    assert len(result) == 1
    assert isinstance(result[0], click.Command)
    assert result[0].name == "schedule"


# =============================================================================
# get_files_for_deploy Tests
# =============================================================================

# The get_files_for_deploy function only reads files from disk (via Path.home()),
# so the mng_ctx parameter is unused. We use a SimpleNamespace as a lightweight
# stand-in since creating a full MngContext would be overkill.
_UNUSED_MNG_CTX = cast(MngContext, SimpleNamespace())


def test_get_files_for_deploy_returns_empty_dict_when_no_mng_files() -> None:
    """get_files_for_deploy returns empty dict when no mng config files exist."""
    result = get_files_for_deploy(mng_ctx=_UNUSED_MNG_CTX, include_user_settings=True)

    assert result == {}


def test_get_files_for_deploy_includes_mng_config() -> None:
    """get_files_for_deploy includes ~/.mng/config.toml when it exists."""
    mng_dir = Path.home() / ".mng"
    mng_dir.mkdir(parents=True, exist_ok=True)
    config_file = mng_dir / "config.toml"
    config_file.write_text("[test]\nkey = 'value'\n")

    result = get_files_for_deploy(mng_ctx=_UNUSED_MNG_CTX, include_user_settings=True)

    assert Path("~/.mng/config.toml") in result
    assert result[Path("~/.mng/config.toml")] == config_file


def test_get_files_for_deploy_includes_mng_profiles() -> None:
    """get_files_for_deploy includes files from ~/.mng/profiles/ when they exist."""
    profiles_dir = Path.home() / ".mng" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_file = profiles_dir / "default"
    profile_file.write_text("profile-data")

    result = get_files_for_deploy(mng_ctx=_UNUSED_MNG_CTX, include_user_settings=True)

    assert Path("~/.mng/profiles/default") in result
    assert result[Path("~/.mng/profiles/default")] == profile_file


def test_get_files_for_deploy_includes_nested_profile_files() -> None:
    """get_files_for_deploy includes nested files from ~/.mng/profiles/."""
    profiles_dir = Path.home() / ".mng" / "profiles" / "subdir"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    nested_file = profiles_dir / "settings.toml"
    nested_file.write_text("nested-data")

    result = get_files_for_deploy(mng_ctx=_UNUSED_MNG_CTX, include_user_settings=True)

    assert Path("~/.mng/profiles/subdir/settings.toml") in result


def test_get_files_for_deploy_returns_empty_when_user_settings_excluded() -> None:
    """get_files_for_deploy returns empty dict when include_user_settings is False."""
    mng_dir = Path.home() / ".mng"
    mng_dir.mkdir(parents=True, exist_ok=True)
    config_file = mng_dir / "config.toml"
    config_file.write_text("[test]\nkey = 'value'\n")

    result = get_files_for_deploy(mng_ctx=_UNUSED_MNG_CTX, include_user_settings=False)

    assert result == {}
