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
def build_check_and_install_packages_command(
    mngr_host_dir: str,
) -> str:
    """Build a single shell command that checks for and installs required packages.

    This command:
    1. Checks for each required package (sshd, tmux, curl, rsync, git)
    2. Echoes a prefixed warning for each missing package
    3. Installs all missing packages in a single apt-get call
    4. Creates the sshd run directory (/run/sshd)
    5. Creates the mngr host directory

    The warning prefix (MNGR_WARN:) can be parsed from the output to display
    warnings to the user about missing packages.

    Returns a shell command string that can be executed via sh -c.
    """
    # Build a shell script that does everything in one command
    # Using semicolons to separate commands so it runs as a single shell invocation
    script_lines = [
        # Initialize the list of packages to install
        "PKGS_TO_INSTALL=''",
        # Check for sshd
        "if ! test -x /usr/sbin/sshd; then "
        f"echo '{WARNING_PREFIX}openssh-server is not pre-installed in the base image. "
        "Installing at runtime. For faster startup, consider using an image with openssh-server pre-installed.'; "
        'PKGS_TO_INSTALL="$PKGS_TO_INSTALL openssh-server"; '
        "fi",
        # Check for tmux
        "if ! command -v tmux >/dev/null 2>&1; then "
        f"echo '{WARNING_PREFIX}tmux is not pre-installed in the base image. "
        "Installing at runtime. For faster startup, consider using an image with tmux pre-installed.'; "
        'PKGS_TO_INSTALL="$PKGS_TO_INSTALL tmux"; '
        "fi",
        # Check for curl
        "if ! command -v curl >/dev/null 2>&1; then "
        f"echo '{WARNING_PREFIX}curl is not pre-installed in the base image. "
        "Installing at runtime. For faster startup, consider using an image with curl pre-installed.'; "
        'PKGS_TO_INSTALL="$PKGS_TO_INSTALL curl"; '
        "fi",
        # Check for rsync
        "if ! command -v rsync >/dev/null 2>&1; then "
        f"echo '{WARNING_PREFIX}rsync is not pre-installed in the base image. "
        "Installing at runtime. For faster startup, consider using an image with rsync pre-installed.'; "
        'PKGS_TO_INSTALL="$PKGS_TO_INSTALL rsync"; '
        "fi",
        # Check for git
        "if ! command -v git >/dev/null 2>&1; then "
        f"echo '{WARNING_PREFIX}git is not pre-installed in the base image. "
        "Installing at runtime. For faster startup, consider using an image with git pre-installed.'; "
        'PKGS_TO_INSTALL="$PKGS_TO_INSTALL git"; '
        "fi",
        # Check for jq (required for activity_watcher.sh to read data.json)
        "if ! command -v jq >/dev/null 2>&1; then "
        f"echo '{WARNING_PREFIX}jq is not pre-installed in the base image. "
        "Installing at runtime. For faster startup, consider using an image with jq pre-installed.'; "
        'PKGS_TO_INSTALL="$PKGS_TO_INSTALL jq"; '
        "fi",
        # Install missing packages if any
        'if [ -n "$PKGS_TO_INSTALL" ]; then apt-get update -qq && apt-get install -y -qq $PKGS_TO_INSTALL; fi',
        # Create sshd run directory (required for sshd to start)
        "mkdir -p /run/sshd",
        # Create mngr host directory
        f"mkdir -p {mngr_host_dir}",
    ]

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


def _load_activity_watcher_script() -> str:
    """Load the activity watcher script from resources."""
    resource_files = importlib.resources.files(resources)
    script_path = resource_files.joinpath("activity_watcher.sh")
    return script_path.read_text()


@pure
def build_start_activity_watcher_command(
    mngr_host_dir: str,
) -> str:
    """Build a shell command that installs and starts the activity watcher.

    The activity watcher monitors activity files and calls the shutdown script
    when the host becomes idle (based on idle_mode and max_idle_seconds
    from data.json).

    This command:
    1. Creates the commands directory
    2. Writes the activity watcher script to the host
    3. Makes it executable
    4. Starts it in the background with nohup

    Returns a shell command string that can be executed via sh -c.
    """
    script_content = _load_activity_watcher_script()

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
