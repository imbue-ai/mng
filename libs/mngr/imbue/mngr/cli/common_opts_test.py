"""Tests for common_opts module."""

from unittest.mock import MagicMock

import click
import pytest
from click.core import ParameterSource

from imbue.mngr.cli.common_opts import _run_pre_command_scripts
from imbue.mngr.cli.common_opts import _run_single_script
from imbue.mngr.cli.common_opts import apply_config_defaults
from imbue.mngr.config.data_types import CommandDefaults
from imbue.mngr.config.data_types import MngrConfig


def test_run_single_script_success() -> None:
    """_run_single_script should return exit code 0 for successful command."""
    script, exit_code, stdout, stderr = _run_single_script("echo hello")
    assert script == "echo hello"
    assert exit_code == 0
    assert "hello" in stdout
    assert stderr == ""


def test_run_single_script_failure() -> None:
    """_run_single_script should return non-zero exit code for failed command."""
    script, exit_code, stdout, stderr = _run_single_script("exit 1")
    assert script == "exit 1"
    assert exit_code == 1


def test_run_single_script_captures_stderr() -> None:
    """_run_single_script should capture stderr from failed command."""
    script, exit_code, stdout, stderr = _run_single_script("echo error >&2 && exit 1")
    assert exit_code == 1
    assert "error" in stderr


def test_run_pre_command_scripts_no_scripts(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should do nothing if no scripts configured."""
    config = MngrConfig(prefix=mngr_test_prefix, pre_command_scripts={})
    # Should not raise
    _run_pre_command_scripts(config, "create")


def test_run_pre_command_scripts_no_scripts_for_command(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should do nothing if no scripts for this command."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        pre_command_scripts={"other_command": ["echo hello"]},
    )
    # Should not raise
    _run_pre_command_scripts(config, "create")


def test_run_pre_command_scripts_success(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should succeed when all scripts pass."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        pre_command_scripts={"create": ["echo first", "echo second"]},
    )
    # Should not raise
    _run_pre_command_scripts(config, "create")


def test_run_pre_command_scripts_single_failure(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should raise ClickException when a script fails."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        pre_command_scripts={"create": ["exit 1"]},
    )
    with pytest.raises(click.ClickException) as exc_info:
        _run_pre_command_scripts(config, "create")
    assert "Pre-command script(s) failed" in str(exc_info.value)
    assert "exit 1" in str(exc_info.value)
    assert "Exit code: 1" in str(exc_info.value)


def test_run_pre_command_scripts_multiple_failures(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should report all failures."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        pre_command_scripts={"create": ["exit 1", "exit 2"]},
    )
    with pytest.raises(click.ClickException) as exc_info:
        _run_pre_command_scripts(config, "create")
    error_message = str(exc_info.value)
    assert "Pre-command script(s) failed" in error_message
    # Both failures should be reported
    assert "exit 1" in error_message or "exit 2" in error_message


def test_run_pre_command_scripts_partial_failure(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should fail even if only one script fails."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        pre_command_scripts={"create": ["echo success", "exit 42"]},
    )
    with pytest.raises(click.ClickException) as exc_info:
        _run_pre_command_scripts(config, "create")
    assert "Exit code: 42" in str(exc_info.value)


def test_run_pre_command_scripts_includes_stderr_in_error(mngr_test_prefix: str) -> None:
    """_run_pre_command_scripts should include stderr in error message."""
    config = MngrConfig(
        prefix=mngr_test_prefix,
        pre_command_scripts={"create": ["echo 'my error message' >&2 && exit 1"]},
    )
    with pytest.raises(click.ClickException) as exc_info:
        _run_pre_command_scripts(config, "create")
    assert "my error message" in str(exc_info.value)


def test_apply_config_defaults_empty_string_clears_tuple_param(mngr_test_prefix: str) -> None:
    """apply_config_defaults should convert empty string to empty tuple for tuple params."""
    # Create a mock context with a tuple parameter
    ctx = MagicMock(spec=click.Context)
    ctx.params = {"add_command": ("default_cmd",), "other_param": "value"}
    ctx.get_parameter_source.return_value = ParameterSource.DEFAULT

    # Create config with empty string for the tuple param (simulating env var override)
    config = MngrConfig(
        prefix=mngr_test_prefix,
        commands={"create": CommandDefaults(defaults={"add_command": ""})},
    )

    result = apply_config_defaults(ctx, config, "create")

    # Empty string should be converted to empty tuple for tuple params
    assert result["add_command"] == ()


def test_apply_config_defaults_non_empty_string_replaces_tuple_param(mngr_test_prefix: str) -> None:
    """apply_config_defaults should replace tuple param with config list value."""
    # Create a mock context with a tuple parameter
    ctx = MagicMock(spec=click.Context)
    ctx.params = {"add_command": (), "other_param": "value"}
    ctx.get_parameter_source.return_value = ParameterSource.DEFAULT

    # Create config with a list value for the tuple param
    config = MngrConfig(
        prefix=mngr_test_prefix,
        commands={"create": CommandDefaults(defaults={"add_command": ["cmd1", "cmd2"]})},
    )

    result = apply_config_defaults(ctx, config, "create")

    # List value should be used directly
    assert result["add_command"] == ["cmd1", "cmd2"]


def test_apply_config_defaults_empty_string_does_not_affect_non_tuple_params(mngr_test_prefix: str) -> None:
    """apply_config_defaults should not convert empty string for non-tuple params."""
    # Create a mock context with a string parameter
    ctx = MagicMock(spec=click.Context)
    ctx.params = {"name": "default_name", "other_param": "value"}
    ctx.get_parameter_source.return_value = ParameterSource.DEFAULT

    # Create config with empty string for the string param
    config = MngrConfig(
        prefix=mngr_test_prefix,
        commands={"create": CommandDefaults(defaults={"name": ""})},
    )

    result = apply_config_defaults(ctx, config, "create")

    # Empty string should be kept as-is for non-tuple params
    assert result["name"] == ""
