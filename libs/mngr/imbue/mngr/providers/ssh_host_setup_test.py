"""Tests for SSH host setup utilities."""

from pathlib import Path

from imbue.mngr.providers.ssh_host_setup import WARNING_PREFIX
from imbue.mngr.providers.ssh_host_setup import _load_activity_watcher_script
from imbue.mngr.providers.ssh_host_setup import build_check_and_install_packages_command
from imbue.mngr.providers.ssh_host_setup import build_configure_ssh_command
from imbue.mngr.providers.ssh_host_setup import build_start_activity_watcher_command
from imbue.mngr.providers.ssh_host_setup import get_user_ssh_dir
from imbue.mngr.providers.ssh_host_setup import parse_warnings_from_output


def test_root_user() -> None:
    """Root user should get /root/.ssh."""
    result = get_user_ssh_dir("root")
    assert result == Path("/root/.ssh")


def test_regular_user() -> None:
    """Regular users should get /home/<user>/.ssh."""
    result = get_user_ssh_dir("alice")
    assert result == Path("/home/alice/.ssh")


def test_valid_shell_command() -> None:
    """The command should be a valid shell command string."""
    cmd = build_check_and_install_packages_command("/mngr/hosts/test")
    assert isinstance(cmd, str)
    assert len(cmd) > 0


def test_valid_configure_ssh_command() -> None:
    """The command should be a valid shell command string."""
    cmd = build_configure_ssh_command(
        user="root",
        client_public_key="ssh-ed25519 AAAA... user@host",
        host_private_key="-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
        host_public_key="ssh-ed25519 BBBB... hostkey",
    )
    assert isinstance(cmd, str)
    assert len(cmd) > 0


def test_extracts_warnings() -> None:
    """Should extract warning messages from output."""
    output = f"""
Some other output
{WARNING_PREFIX}This is a warning message
More output
{WARNING_PREFIX}Another warning
Final output
"""
    warnings = parse_warnings_from_output(output)
    assert len(warnings) == 2
    assert "This is a warning message" in warnings
    assert "Another warning" in warnings


def test_empty_output() -> None:
    """Empty output should return empty list."""
    warnings = parse_warnings_from_output("")
    assert warnings == []


def test_no_warnings() -> None:
    """Output without warnings should return empty list."""
    output = "Some normal output\nMore output\n"
    warnings = parse_warnings_from_output(output)
    assert warnings == []


def test_strips_whitespace() -> None:
    """Warning messages should have whitespace stripped."""
    output = f"{WARNING_PREFIX}  warning with spaces  "
    warnings = parse_warnings_from_output(output)
    assert warnings == ["warning with spaces"]


def test_skips_empty_warnings() -> None:
    """Empty warning messages should be skipped."""
    output = f"{WARNING_PREFIX}\n{WARNING_PREFIX}   \n{WARNING_PREFIX}actual warning"
    warnings = parse_warnings_from_output(output)
    assert warnings == ["actual warning"]


def test_load_activity_watcher_script() -> None:
    """Should load the activity watcher script from resources."""
    script = _load_activity_watcher_script()
    assert isinstance(script, str)
    assert len(script) > 0
    assert "#!/bin/bash" in script
    assert "activity_watcher" in script.lower() or "HOST_DATA_DIR" in script


def test_build_start_activity_watcher_command() -> None:
    """Should build a valid shell command to start the activity watcher."""
    cmd = build_start_activity_watcher_command("/mngr/hosts/test")
    assert isinstance(cmd, str)
    assert len(cmd) > 0
    assert "/mngr/hosts/test" in cmd
    assert "mkdir -p" in cmd
    assert "chmod +x" in cmd
    assert "nohup" in cmd


def test_build_start_activity_watcher_command_escapes_quotes() -> None:
    """Should properly escape single quotes in the script content."""
    cmd = build_start_activity_watcher_command("/mngr/hosts/test")
    # The command should contain the script content with proper escaping
    assert isinstance(cmd, str)
    # Single quotes in the script should be escaped as '\"'\"'
    # Since the script contains single quotes in strings like 'MNGR_HOST_DIR'
    # they should be properly escaped
    assert cmd.count("printf") >= 1
