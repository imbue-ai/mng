"""Tests for SSH host setup utilities."""

from pathlib import Path

from imbue.mngr.providers.ssh_host_setup import WARNING_PREFIX
from imbue.mngr.providers.ssh_host_setup import build_check_and_install_packages_command
from imbue.mngr.providers.ssh_host_setup import build_configure_ssh_command
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
