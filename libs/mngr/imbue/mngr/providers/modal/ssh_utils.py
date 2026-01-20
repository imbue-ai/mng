"""SSH utilities for Modal provider.

Handles SSH key generation and management for Modal sandbox access.
"""

import fcntl
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_ssh_keypair() -> tuple[str, str]:
    """Generate a new RSA keypair for SSH authentication.

    Returns a tuple of (private_key_pem, public_key_openssh).
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_key_openssh = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode("utf-8")
    )
    return private_key_pem, public_key_openssh


def save_ssh_keypair(key_dir: Path, key_name: str = "modal_ssh_key") -> tuple[Path, Path]:
    """Generate and save an SSH keypair to the specified directory.

    Returns a tuple of (private_key_path, public_key_path).
    """
    key_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = key_dir / key_name
    public_key_path = key_dir / f"{key_name}.pub"

    private_key_pem, public_key_openssh = generate_ssh_keypair()

    private_key_path.write_text(private_key_pem)
    private_key_path.chmod(0o600)

    public_key_path.write_text(public_key_openssh)
    public_key_path.chmod(0o644)

    return private_key_path, public_key_path


def load_or_create_ssh_keypair(key_dir: Path, key_name: str = "modal_ssh_key") -> tuple[Path, str]:
    """Load an existing SSH keypair or create a new one if it doesn't exist.

    Returns a tuple of (private_key_path, public_key_content).
    """
    private_key_path = key_dir / key_name
    public_key_path = key_dir / f"{key_name}.pub"

    if private_key_path.exists() and public_key_path.exists():
        return private_key_path, public_key_path.read_text().strip()

    save_ssh_keypair(key_dir, key_name)
    return private_key_path, public_key_path.read_text().strip()


def generate_ed25519_host_keypair() -> tuple[str, str]:
    """Generate a new Ed25519 keypair for SSH host key.

    Returns a tuple of (private_key_pem, public_key_openssh).
    Ed25519 is preferred for SSH host keys due to its security and performance.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_key_openssh = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH,
        )
        .decode("utf-8")
    )
    return private_key_pem, public_key_openssh


def load_or_create_host_keypair(key_dir: Path, key_name: str = "host_key") -> tuple[Path, str]:
    """Load an existing SSH host keypair or create a new one if it doesn't exist.

    This key is used as the SSH host key for all Modal sandboxes, allowing us
    to pre-trust the key and avoid host key verification prompts.

    Returns a tuple of (private_key_path, public_key_content).
    """
    key_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = key_dir / key_name
    public_key_path = key_dir / f"{key_name}.pub"

    if private_key_path.exists() and public_key_path.exists():
        return private_key_path, public_key_path.read_text().strip()

    private_key_pem, public_key_openssh = generate_ed25519_host_keypair()

    private_key_path.write_text(private_key_pem)
    private_key_path.chmod(0o600)

    public_key_path.write_text(public_key_openssh)
    public_key_path.chmod(0o644)

    return private_key_path, public_key_openssh


def add_host_to_known_hosts(
    known_hosts_path: Path,
    hostname: str,
    port: int,
    public_key: str,
) -> None:
    """Add a host entry to the known_hosts file.

    The entry format is: [hostname]:port key_type base64_key
    This allows SSH to verify the host key without prompting.

    Uses file locking to prevent race conditions when multiple processes
    try to update the known_hosts file simultaneously.
    """
    known_hosts_path.parent.mkdir(parents=True, exist_ok=True)

    # Format the host entry - use [host]:port format for non-standard ports
    if port == 22:
        host_pattern = hostname
    else:
        host_pattern = f"[{hostname}]:{port}"

    # The public key should already be in OpenSSH format: "ssh-ed25519 AAAA..."
    entry = f"{host_pattern} {public_key}\n"

    # Use file locking to prevent race conditions
    with open(known_hosts_path, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            # Read existing content to check if entry already exists
            f.seek(0)
            existing_content = f.read()

            # Check if this exact entry already exists
            if entry.strip() not in existing_content:
                # Also check if we already have an entry for this host (might be stale)
                # and remove it before adding the new one
                lines = existing_content.splitlines(keepends=True)
                new_lines = [line for line in lines if not line.startswith(f"{host_pattern} ")]
                new_lines.append(entry)

                # Rewrite the file
                f.seek(0)
                f.truncate()
                f.writelines(new_lines)

            # Ensure the file is flushed to disk before we return
            # This prevents race conditions where paramiko reads a stale version
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
