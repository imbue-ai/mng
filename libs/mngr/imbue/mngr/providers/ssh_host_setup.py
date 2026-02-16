"""SSH host setup utilities for providers.

Contains shell command builders for setting up SSH access on host containers/VMs.
These utilities are designed to be reusable across different providers (Modal, Docker, etc.)
that need to configure SSH access on newly created hosts.
"""

import importlib.resources
from pathlib import Path
from typing import Final

from imbue.imbue_common.pure import pure
from imbue.mngr import resources

# Prefix used in shell output to identify warnings that should be shown to the user
WARNING_PREFIX: Final[str] = "MNGR_WARN:"


@pure
def get_user_ssh_dir(user: str) -> Path:
    """Get the SSH directory path for a given user.

    Returns /root/.ssh for root, /home/<user>/.ssh for others.
    """
    if user == "root":
        return Path("/root/.ssh")
    else:
        return Path(f"/home/{user}/.ssh")


@pure
def _build_package_check_snippet(binary: str, package: str, check_cmd: str | None) -> str:
    """Build a shell snippet that checks for a binary and adds its package to the install list.

    If check_cmd is provided, it is used as the existence check (e.g. "test -x /usr/sbin/sshd").
    Otherwise, "command -v <binary> >/dev/null 2>&1" is used.
    """
    check = check_cmd if check_cmd is not None else f"command -v {binary} >/dev/null 2>&1"
    return (
        f"if ! {check}; then "
        f"echo '{WARNING_PREFIX}{package} is not pre-installed in the base image. "
        f"Installing at runtime. For faster startup, consider using an image with {package} pre-installed.'; "
        f'PKGS_TO_INSTALL="$PKGS_TO_INSTALL {package}"; '
        "fi"
    )


@pure
def build_check_and_install_packages_command(
    mngr_host_dir: str,
    host_volume_mount_path: str | None = None,
) -> str:
    """Build a single shell command that checks for and installs required packages.

    This command:
    1. Checks for each required package (sshd, tmux, curl, rsync, git, jq)
    2. Echoes a prefixed warning for each missing package
    3. Installs all missing packages in a single apt-get call
    4. Creates the sshd run directory (/run/sshd)
    5. Sets up the mngr host directory (either via mkdir or symlink to volume)

    When host_volume_mount_path is provided, the host directory is created as
    a symlink to the volume mount path instead of as a regular directory. This
    causes all data written to host_dir to persist on the volume.

    Returns a shell command string that can be executed via sh -c.
    """
    script_lines = [
        "PKGS_TO_INSTALL=''",
        _build_package_check_snippet(binary="sshd", package="openssh-server", check_cmd="test -x /usr/sbin/sshd"),
        _build_package_check_snippet(binary="tmux", package="tmux", check_cmd=None),
        _build_package_check_snippet(binary="curl", package="curl", check_cmd=None),
        _build_package_check_snippet(binary="rsync", package="rsync", check_cmd=None),
        _build_package_check_snippet(binary="git", package="git", check_cmd=None),
        _build_package_check_snippet(binary="jq", package="jq", check_cmd=None),
        # Install missing packages if any
        'if [ -n "$PKGS_TO_INSTALL" ]; then apt-get update -qq && apt-get install -y -qq $PKGS_TO_INSTALL; fi',
        # Create sshd run directory (required for sshd to start)
        "mkdir -p /run/sshd",
    ]

    if host_volume_mount_path is not None:
        # Remove any existing directory (e.g., from a pre-volume snapshot) before
        # creating the symlink. ln -sfn alone won't replace an existing directory.
        script_lines.append(
            f"[ -L {mngr_host_dir} ] || rm -rf {mngr_host_dir}; ln -sfn {host_volume_mount_path} {mngr_host_dir}"
        )
    else:
        script_lines.append(f"mkdir -p {mngr_host_dir}")

    return "; ".join(script_lines)


@pure
def build_configure_ssh_command(
    user: str,
    client_public_key: str,
    host_private_key: str,
    host_public_key: str,
) -> str:
    """Build a shell command that configures SSH keys and permissions.

    This command:
    1. Creates the user's .ssh directory
    2. Writes the authorized_keys file (for client authentication)
    3. Removes any existing host keys
    4. Installs the provided host key (for host identification)
    5. Sets correct permissions on all files

    Returns a shell command string that can be executed via sh -c.
    """
    ssh_dir = get_user_ssh_dir(user)
    authorized_keys_path = ssh_dir / "authorized_keys"

    # Escape single quotes in keys by ending the quote, adding escaped quote, starting quote again
    # e.g., key'with'quotes becomes key'\''with'\''quotes
    escaped_client_key = client_public_key.replace("'", "'\"'\"'")
    escaped_host_private_key = host_private_key.replace("'", "'\"'\"'")
    escaped_host_public_key = host_public_key.replace("'", "'\"'\"'")

    script_lines = [
        # Create .ssh directory
        f"mkdir -p '{ssh_dir}'",
        # Write authorized_keys file
        f"printf '%s' '{escaped_client_key}' > '{authorized_keys_path}'",
        # Set permissions on authorized_keys
        f"chmod 600 '{authorized_keys_path}'",
        # Remove any existing host keys (important for restored sandboxes)
        "rm -f /etc/ssh/ssh_host_*",
        # Write the host private key
        f"printf '%s' '{escaped_host_private_key}' > /etc/ssh/ssh_host_ed25519_key",
        # Write the host public key
        f"printf '%s' '{escaped_host_public_key}' > /etc/ssh/ssh_host_ed25519_key.pub",
        # Set correct permissions on host keys
        "chmod 600 /etc/ssh/ssh_host_ed25519_key",
        "chmod 644 /etc/ssh/ssh_host_ed25519_key.pub",
    ]

    return "; ".join(script_lines)


@pure
def build_add_known_hosts_command(
    user: str,
    known_hosts_entries: tuple[str, ...],
) -> str | None:
    """Build a shell command that adds entries to the user's known_hosts file.

    This command:
    1. Creates the user's .ssh directory if it doesn't exist
    2. Appends each known_hosts entry to the known_hosts file

    Each entry should be a full known_hosts line (e.g., "github.com ssh-rsa AAAA...")

    Returns a shell command string that can be executed via sh -c, or None if
    there are no entries to add.
    """
    if not known_hosts_entries:
        return None

    ssh_dir = get_user_ssh_dir(user)
    known_hosts_path = ssh_dir / "known_hosts"

    script_lines: list[str] = [
        # Create .ssh directory if needed
        f"mkdir -p '{ssh_dir}'",
    ]

    for entry in known_hosts_entries:
        # Escape single quotes in the entry
        escaped_entry = entry.replace("'", "'\"'\"'")
        # Append entry to known_hosts (with a newline)
        script_lines.append(f"printf '%s\\n' '{escaped_entry}' >> '{known_hosts_path}'")

    # Set proper permissions on known_hosts file
    script_lines.append(f"chmod 600 '{known_hosts_path}'")

    return "; ".join(script_lines)


@pure
def parse_warnings_from_output(output: str) -> list[str]:
    """Parse warning messages from command output.

    Looks for lines prefixed with WARNING_PREFIX and extracts the warning messages.

    Returns a list of warning messages (without the prefix).
    """
    warnings: list[str] = []
    for line in output.split("\n"):
        if line.startswith(WARNING_PREFIX):
            warning_message = line[len(WARNING_PREFIX) :].strip()
            if warning_message:
                warnings.append(warning_message)
    return warnings


def load_resource_script(filename: str) -> str:
    """Load a shell script from the mngr resources package."""
    resource_files = importlib.resources.files(resources)
    script_path = resource_files.joinpath(filename)
    return script_path.read_text()


@pure
def build_start_volume_sync_command(
    volume_mount_path: str,
    mngr_host_dir: str,
) -> str:
    """Build a shell command that starts a background loop to sync the host volume.

    The sync loop runs every 60 seconds and calls 'sync' on the volume mount
    path to flush any pending writes. This ensures data is persisted to the
    volume even if the sandbox is terminated without a clean shutdown.

    Returns a shell command string that can be executed via sh -c.
    """
    script_path = f"{mngr_host_dir}/commands/volume_sync.sh"
    log_path = f"{mngr_host_dir}/logs/volume_sync.log"

    # The sync script content (simple loop)
    sync_script = f"#!/bin/sh\nwhile true; do sync {volume_mount_path} 2>/dev/null; sleep 60; done\n"
    escaped_script = sync_script.replace("'", "'\"'\"'")

    script_lines = [
        f"mkdir -p '{mngr_host_dir}/commands'",
        f"mkdir -p '{mngr_host_dir}/logs'",
        f"printf '%s' '{escaped_script}' > '{script_path}'",
        f"chmod +x '{script_path}'",
        f"nohup '{script_path}' > '{log_path}' 2>&1 &",
    ]

    return "; ".join(script_lines)


@pure
def build_start_activity_watcher_command(
    mngr_host_dir: str,
) -> str:
    """Build a shell command that installs and starts the activity watcher.

    The activity watcher monitors activity files and calls the shutdown script
    when the host becomes idle (based on idle_mode and idle_timeout_seconds
    from data.json).

    This command:
    1. Creates the commands directory
    2. Writes the activity watcher script to the host
    3. Makes it executable
    4. Starts it in the background with nohup

    Returns a shell command string that can be executed via sh -c.
    """
    script_content = load_resource_script("activity_watcher.sh")

    # Escape single quotes in script content
    escaped_script = script_content.replace("'", "'\"'\"'")

    script_path = f"{mngr_host_dir}/commands/activity_watcher.sh"
    log_path = f"{mngr_host_dir}/logs/activity_watcher.log"

    script_lines = [
        # Create commands and logs directories
        f"mkdir -p '{mngr_host_dir}/commands'",
        f"mkdir -p '{mngr_host_dir}/logs'",
        # Write the activity watcher script
        f"printf '%s' '{escaped_script}' > '{script_path}'",
        # Make it executable
        f"chmod +x '{script_path}'",
        # Start the activity watcher in the background, redirecting output to log
        f"nohup '{script_path}' '{mngr_host_dir}' > '{log_path}' 2>&1 &",
    ]

    return "; ".join(script_lines)
