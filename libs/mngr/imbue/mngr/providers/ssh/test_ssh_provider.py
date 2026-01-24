"""Integration tests for the SSH provider using a local sshd instance.

These tests require openssh-server to be installed on the system.
They start a local sshd instance on a random port for testing.
"""

import os
import shutil
import signal
import socket
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.ssh.backend import SSHHostConfig
from imbue.mngr.providers.ssh.instance import SSHProviderInstance
from imbue.mngr.utils.testing import wait_for


def find_free_port() -> int:
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def is_port_open(port: int) -> bool:
    """Check if a port is open and accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", port))
            return True
    except (OSError, socket.timeout):
        return False


@contextmanager
def local_sshd(
    authorized_keys_content: str,
) -> Generator[tuple[int, Path], None, None]:
    """Start a local sshd instance for testing.

    Yields (port, host_key_path) tuple.
    """
    # Check if sshd is available
    sshd_path = shutil.which("sshd")
    if sshd_path is None:
        pytest.skip("sshd not found - install openssh-server")
    # Assert needed for type narrowing since pytest.skip is typed as NoReturn
    assert sshd_path is not None

    # Ensure ~/.ssh directory exists for pyinfra's known_hosts handling
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(exist_ok=True)

    port = find_free_port()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create directories
        etc_dir = tmpdir_path / "etc"
        run_dir = tmpdir_path / "run"
        etc_dir.mkdir()
        run_dir.mkdir()

        # Generate host key
        host_key_path = etc_dir / "ssh_host_ed25519_key"
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(host_key_path),
                "-N",
                "",
                "-q",
            ],
            check=True,
        )

        # Create authorized_keys
        authorized_keys_path = tmpdir_path / "authorized_keys"
        authorized_keys_path.write_text(authorized_keys_content)

        # Create sshd_config
        sshd_config_path = etc_dir / "sshd_config"
        current_user = os.environ.get("USER", "root")
        sshd_config = f"""
Port {port}
ListenAddress 127.0.0.1
HostKey {host_key_path}
AuthorizedKeysFile {authorized_keys_path}
PasswordAuthentication no
ChallengeResponseAuthentication no
UsePAM no
PermitRootLogin yes
PidFile {run_dir}/sshd.pid
StrictModes no
Subsystem sftp /usr/lib/openssh/sftp-server
AllowUsers {current_user}
"""
        sshd_config_path.write_text(sshd_config)

        # Start sshd
        proc = subprocess.Popen(
            [sshd_path, "-D", "-f", str(sshd_config_path), "-e"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            # Wait for sshd to start
            wait_for(
                lambda: is_port_open(port),
                timeout=10.0,
                error_message="sshd failed to start within timeout",
            )

            yield port, host_key_path

        finally:
            # Stop sshd
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


@contextmanager
def ssh_keypair() -> Generator[tuple[Path, Path], None, None]:
    """Generate a temporary SSH keypair for testing.

    Yields (private_key_path, public_key_path) tuple.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        key_path = Path(tmpdir) / "id_ed25519"
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(key_path),
                "-N",
                "",
                "-q",
            ],
            check=True,
        )
        yield key_path, Path(f"{key_path}.pub")


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_ssh_provider_create_and_get_host(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test creating and getting a host via SSH provider."""
    with ssh_keypair() as (private_key, public_key):
        public_key_content = public_key.read_text()

        with local_sshd(public_key_content) as (port, _host_key):
            current_user = os.environ.get("USER", "root")
            provider = SSHProviderInstance(
                name=ProviderInstanceName("ssh-test"),
                host_dir=Path("/tmp/mngr-test"),
                mngr_ctx=temp_mngr_ctx,
                hosts={
                    "localhost": SSHHostConfig(
                        address="127.0.0.1",
                        port=port,
                        user=current_user,
                        key_file=private_key,
                    ),
                },
                local_state_dir=temp_host_dir,
            )

            # Create host
            host = provider.create_host(HostName("localhost"))
            assert host is not None
            assert host.id is not None

            # Get host by ID
            retrieved_host = provider.get_host(host.id)
            assert retrieved_host.id == host.id

            # Get host by name
            retrieved_host_by_name = provider.get_host(HostName("localhost"))
            assert retrieved_host_by_name.id == host.id

            # List hosts
            hosts = provider.list_hosts()
            assert len(hosts) == 1
            assert hosts[0].id == host.id

            # Destroy host
            provider.destroy_host(host)

            # Should no longer be listed
            hosts = provider.list_hosts()
            assert len(hosts) == 0


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_ssh_provider_execute_command(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test executing a command on an SSH host."""
    with ssh_keypair() as (private_key, public_key):
        public_key_content = public_key.read_text()

        with local_sshd(public_key_content) as (port, _host_key):
            current_user = os.environ.get("USER", "root")
            provider = SSHProviderInstance(
                name=ProviderInstanceName("ssh-test"),
                host_dir=Path("/tmp/mngr-test"),
                mngr_ctx=temp_mngr_ctx,
                hosts={
                    "localhost": SSHHostConfig(
                        address="127.0.0.1",
                        port=port,
                        user=current_user,
                        key_file=private_key,
                    ),
                },
                local_state_dir=temp_host_dir,
            )

            host = provider.create_host(HostName("localhost"))
            try:
                # Execute a simple command
                result = host.execute_command("echo hello")
                assert result.success
                assert "hello" in result.stdout
            finally:
                provider.destroy_host(host)


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_ssh_provider_double_create_fails(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test that creating a host twice fails."""
    with ssh_keypair() as (private_key, public_key):
        public_key_content = public_key.read_text()

        with local_sshd(public_key_content) as (port, _host_key):
            current_user = os.environ.get("USER", "root")
            provider = SSHProviderInstance(
                name=ProviderInstanceName("ssh-test"),
                host_dir=Path("/tmp/mngr-test"),
                mngr_ctx=temp_mngr_ctx,
                hosts={
                    "localhost": SSHHostConfig(
                        address="127.0.0.1",
                        port=port,
                        user=current_user,
                        key_file=private_key,
                    ),
                },
                local_state_dir=temp_host_dir,
            )

            host = provider.create_host(HostName("localhost"))
            try:
                # Creating again should fail
                with pytest.raises(UserInputError) as exc_info:
                    provider.create_host(HostName("localhost"))
                assert "already registered" in str(exc_info.value)
            finally:
                provider.destroy_host(host)


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_ssh_provider_start_host(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test starting an already-registered host."""
    with ssh_keypair() as (private_key, public_key):
        public_key_content = public_key.read_text()

        with local_sshd(public_key_content) as (port, _host_key):
            current_user = os.environ.get("USER", "root")
            provider = SSHProviderInstance(
                name=ProviderInstanceName("ssh-test"),
                host_dir=Path("/tmp/mngr-test"),
                mngr_ctx=temp_mngr_ctx,
                hosts={
                    "localhost": SSHHostConfig(
                        address="127.0.0.1",
                        port=port,
                        user=current_user,
                        key_file=private_key,
                    ),
                },
                local_state_dir=temp_host_dir,
            )

            host1 = provider.create_host(HostName("localhost"))
            try:
                # start_host should return the same host
                host2 = provider.start_host(host1.id)
                assert host2.id == host1.id
            finally:
                provider.destroy_host(host1)


@pytest.mark.integration
@pytest.mark.timeout(60)
def test_ssh_provider_destroy_removes_state(temp_host_dir: Path, temp_mngr_ctx: MngrContext) -> None:
    """Test that destroying a host removes its state."""
    with ssh_keypair() as (private_key, public_key):
        public_key_content = public_key.read_text()

        with local_sshd(public_key_content) as (port, _host_key):
            current_user = os.environ.get("USER", "root")
            provider = SSHProviderInstance(
                name=ProviderInstanceName("ssh-test"),
                host_dir=Path("/tmp/mngr-test"),
                mngr_ctx=temp_mngr_ctx,
                hosts={
                    "localhost": SSHHostConfig(
                        address="127.0.0.1",
                        port=port,
                        user=current_user,
                        key_file=private_key,
                    ),
                },
                local_state_dir=temp_host_dir,
            )

            host = provider.create_host(HostName("localhost"))
            host_id = host.id

            # State file should exist
            state_path = temp_host_dir / "providers" / "ssh" / "localhost.json"
            assert state_path.exists()

            # Destroy the host
            provider.destroy_host(host_id)

            # State file should be gone
            assert not state_path.exists()

            # Getting the host should fail
            with pytest.raises(HostNotFoundError):
                provider.get_host(host_id)
