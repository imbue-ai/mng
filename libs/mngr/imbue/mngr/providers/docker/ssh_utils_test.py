"""Unit tests for Docker SSH utilities."""

from pathlib import Path

from imbue.mngr.providers.docker.ssh_utils import add_host_to_known_hosts
from imbue.mngr.providers.docker.ssh_utils import generate_ed25519_host_keypair
from imbue.mngr.providers.docker.ssh_utils import generate_ssh_keypair
from imbue.mngr.providers.docker.ssh_utils import load_or_create_host_keypair
from imbue.mngr.providers.docker.ssh_utils import load_or_create_ssh_keypair
from imbue.mngr.providers.docker.ssh_utils import save_ssh_keypair


def test_generate_ssh_keypair() -> None:
    """Test generating an SSH keypair."""
    private_key, public_key = generate_ssh_keypair()

    assert private_key.startswith("-----BEGIN RSA PRIVATE KEY-----")
    assert "ssh-rsa" in public_key


def test_generate_ed25519_host_keypair() -> None:
    """Test generating an Ed25519 host keypair."""
    private_key, public_key = generate_ed25519_host_keypair()

    assert "PRIVATE KEY" in private_key
    assert "ssh-ed25519" in public_key


def test_save_ssh_keypair(tmp_path: Path) -> None:
    """Test saving an SSH keypair to disk."""
    private_path, public_path = save_ssh_keypair(tmp_path)

    assert private_path.exists()
    assert public_path.exists()

    # Check permissions
    assert (private_path.stat().st_mode & 0o777) == 0o600
    assert (public_path.stat().st_mode & 0o777) == 0o644


def test_load_or_create_ssh_keypair_creates_new(tmp_path: Path) -> None:
    """Test that load_or_create creates a new keypair when none exists."""
    private_path, public_key = load_or_create_ssh_keypair(tmp_path)

    assert private_path.exists()
    assert "ssh-rsa" in public_key


def test_load_or_create_ssh_keypair_loads_existing(tmp_path: Path) -> None:
    """Test that load_or_create loads existing keypair."""
    # First create a keypair
    private_path1, public_key1 = load_or_create_ssh_keypair(tmp_path)

    # Then load it again
    private_path2, public_key2 = load_or_create_ssh_keypair(tmp_path)

    assert private_path1 == private_path2
    assert public_key1 == public_key2


def test_load_or_create_host_keypair_creates_new(tmp_path: Path) -> None:
    """Test that load_or_create_host_keypair creates a new keypair when none exists."""
    private_path, public_key = load_or_create_host_keypair(tmp_path)

    assert private_path.exists()
    assert "ssh-ed25519" in public_key


def test_load_or_create_host_keypair_loads_existing(tmp_path: Path) -> None:
    """Test that load_or_create_host_keypair loads existing keypair."""
    # First create a keypair
    private_path1, public_key1 = load_or_create_host_keypair(tmp_path)

    # Then load it again
    private_path2, public_key2 = load_or_create_host_keypair(tmp_path)

    assert private_path1 == private_path2
    assert public_key1 == public_key2


def test_add_host_to_known_hosts_creates_file(tmp_path: Path) -> None:
    """Test that add_host_to_known_hosts creates the file if it doesn't exist."""
    known_hosts_path = tmp_path / "known_hosts"
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGi... test@example.com"

    add_host_to_known_hosts(known_hosts_path, "example.com", 22, public_key)

    assert known_hosts_path.exists()
    content = known_hosts_path.read_text()
    assert "example.com" in content
    assert public_key in content


def test_add_host_to_known_hosts_non_standard_port(tmp_path: Path) -> None:
    """Test that add_host_to_known_hosts handles non-standard ports."""
    known_hosts_path = tmp_path / "known_hosts"
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGi... test@example.com"

    add_host_to_known_hosts(known_hosts_path, "localhost", 2222, public_key)

    content = known_hosts_path.read_text()
    assert "[localhost]:2222" in content


def test_add_host_to_known_hosts_does_not_duplicate(tmp_path: Path) -> None:
    """Test that add_host_to_known_hosts doesn't add duplicate entries."""
    known_hosts_path = tmp_path / "known_hosts"
    public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGi... test@example.com"

    # Add the same entry twice
    add_host_to_known_hosts(known_hosts_path, "example.com", 22, public_key)
    add_host_to_known_hosts(known_hosts_path, "example.com", 22, public_key)

    content = known_hosts_path.read_text()
    # Should only appear once
    assert content.count(public_key) == 1


def test_add_host_to_known_hosts_replaces_old_entry(tmp_path: Path) -> None:
    """Test that add_host_to_known_hosts replaces old entries for the same host."""
    known_hosts_path = tmp_path / "known_hosts"
    old_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOld... test@example.com"
    new_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAInew... test@example.com"

    # Add old entry
    add_host_to_known_hosts(known_hosts_path, "example.com", 22, old_key)

    # Add new entry for same host
    add_host_to_known_hosts(known_hosts_path, "example.com", 22, new_key)

    content = known_hosts_path.read_text()
    # Old key should be gone
    assert old_key not in content
    # New key should be present
    assert new_key in content
