"""Tests for SSH host setup utilities."""

from pathlib import Path

from imbue.mngr.providers.ssh_host_setup import WARNING_PREFIX
from imbue.mngr.providers.ssh_host_setup import build_check_and_install_packages_command
from imbue.mngr.providers.ssh_host_setup import build_configure_ssh_command
from imbue.mngr.providers.ssh_host_setup import get_user_ssh_dir
from imbue.mngr.providers.ssh_host_setup import parse_warnings_from_output


class TestGetUserSshDir:
    def test_root_user(self) -> None:
        """Root user should get /root/.ssh."""
        result = get_user_ssh_dir("root")
        assert result == Path("/root/.ssh")

    def test_regular_user(self) -> None:
        """Regular users should get /home/<user>/.ssh."""
        result = get_user_ssh_dir("alice")
        assert result == Path("/home/alice/.ssh")

    def test_another_user(self) -> None:
        """Test with another regular user."""
        result = get_user_ssh_dir("bob")
        assert result == Path("/home/bob/.ssh")


class TestBuildCheckAndInstallPackagesCommand:
    def test_generates_valid_shell_command(self) -> None:
        """The command should be a valid shell command string."""
        cmd = build_check_and_install_packages_command("/mngr/hosts/test")
        assert isinstance(cmd, str)
        assert len(cmd) > 0

    def test_checks_for_all_required_packages(self) -> None:
        """The command should check for sshd, tmux, curl, rsync, and git."""
        cmd = build_check_and_install_packages_command("/mngr/hosts/test")
        # Check that it tests for each package
        assert "/usr/sbin/sshd" in cmd
        assert "command -v tmux" in cmd
        assert "command -v curl" in cmd
        assert "command -v rsync" in cmd
        assert "command -v git" in cmd

    def test_includes_warning_prefix(self) -> None:
        """Warnings should include the warning prefix."""
        cmd = build_check_and_install_packages_command("/mngr/hosts/test")
        assert WARNING_PREFIX in cmd

    def test_creates_sshd_run_directory(self) -> None:
        """Should create /run/sshd directory."""
        cmd = build_check_and_install_packages_command("/mngr/hosts/test")
        assert "mkdir -p /run/sshd" in cmd

    def test_creates_mngr_host_directory(self) -> None:
        """Should create the mngr host directory."""
        cmd = build_check_and_install_packages_command("/mngr/hosts/test")
        assert "mkdir -p /mngr/hosts/test" in cmd

    def test_apt_install_command(self) -> None:
        """Should include apt-get install for missing packages."""
        cmd = build_check_and_install_packages_command("/mngr/hosts/test")
        assert "apt-get update" in cmd
        assert "apt-get install" in cmd


class TestBuildConfigureSshCommand:
    def test_generates_valid_shell_command(self) -> None:
        """The command should be a valid shell command string."""
        cmd = build_configure_ssh_command(
            user="root",
            client_public_key="ssh-ed25519 AAAA... user@host",
            host_private_key="-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
            host_public_key="ssh-ed25519 BBBB... hostkey",
        )
        assert isinstance(cmd, str)
        assert len(cmd) > 0

    def test_creates_root_ssh_directory(self) -> None:
        """Should create /root/.ssh for root user."""
        cmd = build_configure_ssh_command(
            user="root",
            client_public_key="ssh-ed25519 AAAA...",
            host_private_key="private",
            host_public_key="public",
        )
        assert "/root/.ssh" in cmd

    def test_creates_regular_user_ssh_directory(self) -> None:
        """Should create /home/<user>/.ssh for regular users."""
        cmd = build_configure_ssh_command(
            user="alice",
            client_public_key="ssh-ed25519 AAAA...",
            host_private_key="private",
            host_public_key="public",
        )
        assert "/home/alice/.ssh" in cmd
        assert "/root/.ssh" not in cmd

    def test_sets_authorized_keys_permissions(self) -> None:
        """Should set permissions on authorized_keys."""
        cmd = build_configure_ssh_command(
            user="root",
            client_public_key="ssh-ed25519 AAAA...",
            host_private_key="private",
            host_public_key="public",
        )
        assert "chmod 600" in cmd
        assert "authorized_keys" in cmd

    def test_removes_existing_host_keys(self) -> None:
        """Should remove existing host keys."""
        cmd = build_configure_ssh_command(
            user="root",
            client_public_key="ssh-ed25519 AAAA...",
            host_private_key="private",
            host_public_key="public",
        )
        assert "rm -f /etc/ssh/ssh_host_*" in cmd

    def test_installs_host_keys(self) -> None:
        """Should install host keys with correct permissions."""
        cmd = build_configure_ssh_command(
            user="root",
            client_public_key="ssh-ed25519 AAAA...",
            host_private_key="private",
            host_public_key="public",
        )
        assert "ssh_host_ed25519_key" in cmd
        assert "ssh_host_ed25519_key.pub" in cmd
        assert "chmod 600 /etc/ssh/ssh_host_ed25519_key" in cmd
        assert "chmod 644 /etc/ssh/ssh_host_ed25519_key.pub" in cmd

    def test_escapes_single_quotes_in_keys(self) -> None:
        """Single quotes in keys should be properly escaped."""
        cmd = build_configure_ssh_command(
            user="root",
            client_public_key="key'with'quotes",
            host_private_key="private'key",
            host_public_key="public'key",
        )
        # The escaped version should replace ' with '"'"'
        assert "'\"'\"'" in cmd


class TestParseWarningsFromOutput:
    def test_extracts_warnings(self) -> None:
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

    def test_empty_output(self) -> None:
        """Empty output should return empty list."""
        warnings = parse_warnings_from_output("")
        assert warnings == []

    def test_no_warnings(self) -> None:
        """Output without warnings should return empty list."""
        output = "Some normal output\nMore output\n"
        warnings = parse_warnings_from_output(output)
        assert warnings == []

    def test_strips_whitespace(self) -> None:
        """Warning messages should have whitespace stripped."""
        output = f"{WARNING_PREFIX}  warning with spaces  "
        warnings = parse_warnings_from_output(output)
        assert warnings == ["warning with spaces"]

    def test_skips_empty_warnings(self) -> None:
        """Empty warning messages should be skipped."""
        output = f"{WARNING_PREFIX}\n{WARNING_PREFIX}   \n{WARNING_PREFIX}actual warning"
        warnings = parse_warnings_from_output(output)
        assert warnings == ["actual warning"]
