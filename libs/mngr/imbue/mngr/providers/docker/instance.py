"""Docker provider instance implementation.

Manages Docker containers as hosts with SSH access via pyinfra.
"""

import argparse
import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from typing import Final
from typing import Mapping
from typing import Sequence

from loguru import logger
from pydantic import Field
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State as PyinfraState
from pyinfra.api.inventory import Inventory
from pyinfra.connectors.sshuserclient.client import get_host_keys

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.data_types import CpuResources
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import PyinfraConnector
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ImageReference
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId
from imbue.mngr.providers.base_provider import BaseProviderInstance
from imbue.mngr.providers.docker.ssh_utils import add_host_to_known_hosts
from imbue.mngr.providers.docker.ssh_utils import load_or_create_host_keypair
from imbue.mngr.providers.docker.ssh_utils import load_or_create_ssh_keypair

# Constants
CONTAINER_SSH_PORT: Final[int] = 22
# Seconds to wait for sshd to be ready
SSH_CONNECT_TIMEOUT: Final[int] = 60
# Default base image
DEFAULT_IMAGE: Final[str] = "debian:bookworm-slim"

# Label key constants for container metadata stored in Docker labels
LABEL_PREFIX: Final[str] = "mngr."
LABEL_HOST_ID: Final[str] = f"{LABEL_PREFIX}host_id"
LABEL_HOST_NAME: Final[str] = f"{LABEL_PREFIX}host_name"
LABEL_HOST_RECORD: Final[str] = f"{LABEL_PREFIX}host_record"


class ContainerConfig(FrozenModel):
    """Configuration parsed from build arguments."""

    cpu: float | None = None
    memory: float | None = None
    image: str = DEFAULT_IMAGE


class DockerProviderInstance(BaseProviderInstance):
    """Provider instance for managing Docker containers as hosts.

    Each container runs sshd and is accessed via pyinfra's SSH connector.
    Container metadata (host_id, name, SSH info) is stored in Docker labels
    at creation time.

    Note: Docker labels cannot be modified after container creation, so mutable
    tags are stored in local files.
    """

    container_prefix: str = Field(frozen=True, description="Prefix for container names")
    default_cpu: float | None = Field(frozen=True, description="Default CPU limit (None for no limit)")
    default_memory: float | None = Field(frozen=True, description="Default memory limit in GB (None for no limit)")

    @property
    def supports_snapshots(self) -> bool:
        return False

    @property
    def supports_volumes(self) -> bool:
        return False

    @property
    def supports_mutable_tags(self) -> bool:
        return True

    @property
    def _keys_dir(self) -> Path:
        """Get the directory for storing SSH keys."""
        config_dir = self.mngr_ctx.config.default_host_dir.expanduser()
        return config_dir / "providers" / "docker"

    @property
    def _data_dir(self) -> Path:
        """Get the directory for storing host data (tags, etc)."""
        return self._keys_dir / "hosts"

    def _get_host_data_dir(self, host_id: HostId) -> Path:
        """Get the data directory for a specific host."""
        return self._data_dir / str(host_id)

    def _get_ssh_keypair(self) -> tuple[Path, str]:
        """Get or create the SSH keypair for this provider instance."""
        return load_or_create_ssh_keypair(self._keys_dir)

    def _get_host_keypair(self) -> tuple[Path, str]:
        """Get or create the SSH host keypair for Docker containers."""
        return load_or_create_host_keypair(self._keys_dir)

    @property
    def _known_hosts_path(self) -> Path:
        """Get the path to the known_hosts file for this provider instance."""
        return self._keys_dir / "known_hosts"

    def _parse_build_args(
        self,
        build_args: Sequence[str] | None,
    ) -> ContainerConfig:
        """Parse build arguments into container configuration."""
        if not build_args:
            return ContainerConfig(
                cpu=self.default_cpu,
                memory=self.default_memory,
                image=DEFAULT_IMAGE,
            )

        # Normalize arguments: convert "key=value" to "--key=value"
        normalized_args: list[str] = []
        for arg in build_args:
            if "=" in arg and not arg.startswith("-"):
                normalized_args.append(f"--{arg}")
            else:
                normalized_args.append(arg)

        parser = argparse.ArgumentParser(
            prog="build_args",
            add_help=False,
            exit_on_error=False,
        )
        parser.add_argument("--cpu", type=float, default=self.default_cpu)
        parser.add_argument("--memory", type=float, default=self.default_memory)
        parser.add_argument("--image", type=str, default=DEFAULT_IMAGE)

        try:
            parsed, unknown = parser.parse_known_args(normalized_args)
        except argparse.ArgumentError as e:
            raise MngrError(f"Invalid build argument: {e}") from None

        if unknown:
            raise MngrError(f"Unknown build arguments: {unknown}")

        return ContainerConfig(
            cpu=parsed.cpu,
            memory=parsed.memory,
            image=parsed.image,
        )

    def _get_container_name(self, host_id: HostId) -> str:
        """Generate a container name from host ID."""
        return f"{self.container_prefix}-{str(host_id)[-8:]}"

    def _run_docker_command(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a docker command and return the result."""
        cmd = ["docker"] + args
        logger.trace("Running docker command: {}", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error("Docker command failed: {} (stderr: {})", e, e.stderr)
            raise MngrError(f"Docker command failed: {e.stderr}") from e

    def _docker_exec(
        self,
        container_name: str,
        command: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a command in a running container."""
        return self._run_docker_command(
            ["exec", container_name] + command,
            check=check,
        )

    def _find_container_by_host_id(self, host_id: HostId) -> dict[str, Any] | None:
        """Find a Docker container by its mngr host_id label."""
        logger.trace("Looking up container with host_id={}", host_id)
        result = self._run_docker_command(
            [
                "ps",
                "-a",
                "--filter",
                f"label={LABEL_HOST_ID}={host_id}",
                "--format",
                "{{json .}}",
            ],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Return the first matching container
        for line in result.stdout.strip().split("\n"):
            if line:
                return json.loads(line)
        return None

    def _find_container_by_name(self, name: HostName) -> dict[str, Any] | None:
        """Find a Docker container by its mngr host_name label."""
        logger.trace("Looking up container with name={}", name)
        result = self._run_docker_command(
            [
                "ps",
                "-a",
                "--filter",
                f"label={LABEL_HOST_NAME}={name}",
                "--format",
                "{{json .}}",
            ],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        for line in result.stdout.strip().split("\n"):
            if line:
                return json.loads(line)
        return None

    def _list_mngr_containers(self) -> list[dict[str, Any]]:
        """List all Docker containers managed by this mngr provider instance."""
        logger.trace("Listing all mngr containers with prefix={}", self.container_prefix)
        result = self._run_docker_command(
            [
                "ps",
                "-a",
                "--filter",
                f"label={LABEL_HOST_ID}",
                "--filter",
                f"name={self.container_prefix}",
                "--format",
                "{{json .}}",
            ],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        containers = []
        for line in result.stdout.strip().split("\n"):
            if line:
                containers.append(json.loads(line))
        return containers

    def _get_container_labels(self, container_name: str) -> dict[str, str]:
        """Get labels from a container."""
        result = self._run_docker_command(
            ["inspect", "--format", "{{json .Config.Labels}}", container_name],
            check=False,
        )
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout.strip())

    def _get_container_port_mapping(self, container_name: str) -> int | None:
        """Get the host port mapped to container SSH port."""
        result = self._run_docker_command(
            ["port", container_name, str(CONTAINER_SSH_PORT)],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Output is like "0.0.0.0:32768" or "[::]:32768"
        port_mapping = result.stdout.strip()
        if ":" in port_mapping:
            return int(port_mapping.rsplit(":", 1)[1])
        return None

    def _is_container_running(self, container_name: str) -> bool:
        """Check if a container is running."""
        result = self._run_docker_command(
            ["inspect", "--format", "{{.State.Running}}", container_name],
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _wait_for_sshd(self, hostname: str, port: int, timeout_seconds: float = SSH_CONNECT_TIMEOUT) -> None:
        """Wait for sshd to be ready to accept connections."""
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.settimeout(2.0)
                sock.connect((hostname, port))
                banner = sock.recv(256)
                if banner.startswith(b"SSH-"):
                    return
            except (OSError, TimeoutError):
                pass
            finally:
                sock.close()
        raise MngrError(f"SSH server not ready after {timeout_seconds}s at {hostname}:{port}")

    def _create_pyinfra_host(self, hostname: str, port: int, private_key_path: Path) -> PyinfraHost:
        """Create a pyinfra host with SSH connector."""
        # Clear pyinfra's memoized known_hosts cache
        known_hosts_path_str = str(self._known_hosts_path)
        cache_key = f"('{known_hosts_path_str}',){{}}"
        if cache_key in get_host_keys.cache:
            del get_host_keys.cache[cache_key]

        host_data = {
            "ssh_user": "root",
            "ssh_port": port,
            "ssh_key": str(private_key_path),
            "ssh_known_hosts_file": known_hosts_path_str,
            "ssh_strict_host_key_checking": "yes",
        }

        names_data = ([(hostname, host_data)], {})
        inventory = Inventory(names_data)
        state = PyinfraState(inventory=inventory)

        pyinfra_host = inventory.get_host(hostname)
        pyinfra_host.init(state)

        return pyinfra_host

    def _build_container_labels(
        self,
        host_id: HostId,
        name: HostName,
        ssh_port: int,
        host_public_key: str,
        config: ContainerConfig,
    ) -> dict[str, str]:
        """Build the labels dict to store on a Docker container."""
        host_record: dict[str, Any] = {
            "ssh_port": ssh_port,
            "ssh_host_public_key": host_public_key,
            "config": {
                "cpu": config.cpu,
                "memory": config.memory,
                "image": config.image,
            },
        }

        return {
            LABEL_HOST_ID: str(host_id),
            LABEL_HOST_NAME: str(name),
            LABEL_HOST_RECORD: json.dumps(host_record),
        }

    def _parse_container_labels(
        self,
        labels: dict[str, str],
    ) -> tuple[HostId, HostName, int, str | None, ContainerConfig]:
        """Parse labels from a Docker container into structured data."""
        host_id = HostId(labels[LABEL_HOST_ID])
        name = HostName(labels[LABEL_HOST_NAME])

        host_record = json.loads(labels[LABEL_HOST_RECORD])
        ssh_port = host_record["ssh_port"]
        host_public_key = host_record.get("ssh_host_public_key")
        config_data = host_record.get("config", {})
        config = ContainerConfig(
            cpu=config_data.get("cpu"),
            memory=config_data.get("memory"),
            image=config_data.get("image", DEFAULT_IMAGE),
        )

        return host_id, name, ssh_port, host_public_key, config

    def _check_and_install_packages(self, container_name: str) -> None:
        """Check for required packages and install if missing."""
        # Check if sshd is installed
        sshd_result = self._docker_exec(
            container_name,
            ["sh", "-c", "test -x /usr/sbin/sshd && echo yes || echo no"],
            check=False,
        )
        is_sshd_installed = sshd_result.stdout.strip() == "yes"

        # Check if tmux is installed
        tmux_result = self._docker_exec(
            container_name,
            ["sh", "-c", "command -v tmux >/dev/null 2>&1 && echo yes || echo no"],
            check=False,
        )
        is_tmux_installed = tmux_result.stdout.strip() == "yes"

        packages_to_install: list[str] = []
        if not is_sshd_installed:
            logger.warning(
                "openssh-server is not pre-installed in the base image. "
                "Installing at runtime. For faster startup, use an image with openssh-server pre-installed."
            )
            packages_to_install.append("openssh-server")

        if not is_tmux_installed:
            logger.warning(
                "tmux is not pre-installed in the base image. "
                "Installing at runtime. For faster startup, use an image with tmux pre-installed."
            )
            packages_to_install.append("tmux")

        if packages_to_install:
            logger.debug("Installing packages: {}", packages_to_install)
            self._docker_exec(container_name, ["apt-get", "update", "-qq"])
            self._docker_exec(container_name, ["apt-get", "install", "-y", "-qq"] + packages_to_install)

        # Create sshd run directory
        self._docker_exec(container_name, ["mkdir", "-p", "/run/sshd"])

        # Create mngr host directory
        self._docker_exec(container_name, ["mkdir", "-p", str(self.host_dir)])

    def _setup_ssh_in_container(
        self,
        container_name: str,
        client_public_key: str,
        host_private_key: str,
        host_public_key: str,
    ) -> None:
        """Set up SSH access in the container."""
        # Check and install required packages
        self._check_and_install_packages(container_name)

        # Create .ssh directory
        self._docker_exec(container_name, ["mkdir", "-p", "/root/.ssh"])

        # Write authorized_keys
        self._run_docker_command([
            "exec",
            "-i",
            container_name,
            "sh",
            "-c",
            f"echo '{client_public_key}' > /root/.ssh/authorized_keys",
        ])

        # Remove any existing host keys
        self._docker_exec(container_name, ["rm", "-f", "/etc/ssh/ssh_host_ed25519_key", "/etc/ssh/ssh_host_ed25519_key.pub"], check=False)

        # Write host keys - use stdin to avoid quoting issues
        self._run_docker_command([
            "exec",
            "-i",
            container_name,
            "sh",
            "-c",
            f"cat > /etc/ssh/ssh_host_ed25519_key << 'EOFKEY'\n{host_private_key}\nEOFKEY",
        ])
        self._run_docker_command([
            "exec",
            "-i",
            container_name,
            "sh",
            "-c",
            f"echo '{host_public_key}' > /etc/ssh/ssh_host_ed25519_key.pub",
        ])

        # Set permissions
        self._docker_exec(container_name, ["chmod", "600", "/etc/ssh/ssh_host_ed25519_key"])
        self._docker_exec(container_name, ["chmod", "644", "/etc/ssh/ssh_host_ed25519_key.pub"])

        # Start sshd in the background
        self._docker_exec(container_name, ["sh", "-c", "/usr/sbin/sshd"])

    def _create_host_from_container(
        self,
        container_info: dict[str, Any],
    ) -> Host | None:
        """Create a Host object from container info."""
        container_name = container_info.get("Names", "")
        if not container_name:
            return None

        labels = self._get_container_labels(container_name)
        if LABEL_HOST_ID not in labels:
            return None

        host_id, name, ssh_port, host_public_key, config = self._parse_container_labels(labels)

        if host_public_key is None:
            logger.debug("Skipping container {} - no host public key in labels", container_name)
            return None

        # Check if container is running
        if not self._is_container_running(container_name):
            logger.debug("Container {} is not running", container_name)
            return None

        # Get the actual port mapping
        actual_port = self._get_container_port_mapping(container_name)
        if actual_port is None:
            logger.debug("No port mapping found for container {}", container_name)
            return None

        # Add the host key to known_hosts
        add_host_to_known_hosts(self._known_hosts_path, "localhost", actual_port, host_public_key)

        private_key_path, _ = self._get_ssh_keypair()
        pyinfra_host = self._create_pyinfra_host("localhost", actual_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        return Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

    # =========================================================================
    # Tag Management (stored in local files since Docker labels are immutable)
    # =========================================================================

    def _get_tags_file_path(self, host_id: HostId) -> Path:
        """Get the path to the tags file for a host."""
        return self._get_host_data_dir(host_id) / "tags.json"

    def _load_tags(self, host_id: HostId) -> dict[str, str]:
        """Load tags from local storage."""
        tags_file = self._get_tags_file_path(host_id)
        if not tags_file.exists():
            return {}
        content = tags_file.read_text()
        if not content.strip():
            return {}
        return json.loads(content)

    def _save_tags(self, host_id: HostId, tags: dict[str, str]) -> None:
        """Save tags to local storage."""
        tags_file = self._get_tags_file_path(host_id)
        tags_file.parent.mkdir(parents=True, exist_ok=True)
        tags_file.write_text(json.dumps(tags, indent=2))

    def _delete_host_data(self, host_id: HostId) -> None:
        """Delete all local data for a host."""
        import shutil

        host_data_dir = self._get_host_data_dir(host_id)
        if host_data_dir.exists():
            shutil.rmtree(host_data_dir)

    # =========================================================================
    # Core Lifecycle Methods
    # =========================================================================

    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
    ) -> Host:
        """Create a new Docker container host."""
        logger.info("Creating Docker container host: name={}", name)

        # Parse build arguments
        config = self._parse_build_args(build_args)
        base_image = str(image) if image else config.image

        # Get SSH client keypair
        private_key_path, client_public_key = self._get_ssh_keypair()
        logger.debug("Using SSH client key: {}", private_key_path)

        # Get SSH host keypair
        host_key_path, host_public_key = self._get_host_keypair()
        host_private_key = host_key_path.read_text()
        logger.debug("Using SSH host key: {}", host_key_path)

        # Generate host ID and container name
        host_id = HostId.generate()
        container_name = self._get_container_name(host_id)

        # Build docker run command
        docker_args: list[str] = [
            "run",
            "-d",
            "--name",
            container_name,
            "-P",  # Publish all exposed ports
        ]

        # Add resource limits
        if config.cpu is not None:
            docker_args.extend(["--cpus", str(config.cpu)])
        if config.memory is not None:
            memory_mb = int(config.memory * 1024)
            docker_args.extend(["--memory", f"{memory_mb}m"])

        # We need a placeholder port for the label - actual port determined after container starts
        # Build labels (note: we'll update the port after container starts)
        container_labels = self._build_container_labels(
            host_id=host_id,
            name=name,
            ssh_port=0,  # Will be determined after container starts
            host_public_key=host_public_key,
            config=config,
        )

        # Add labels
        for key, value in container_labels.items():
            docker_args.extend(["--label", f"{key}={value}"])

        # Add the image and command to keep container running
        docker_args.extend([base_image, "sleep", "infinity"])

        # Create the container
        logger.debug("Creating container with command: docker {}", " ".join(docker_args))
        self._run_docker_command(docker_args)
        logger.info("Created container: {}", container_name)

        # Get the SSH port mapping
        ssh_port = self._get_container_port_mapping(container_name)
        if ssh_port is None:
            # Container doesn't expose port 22 by default, we need to commit and recreate
            # Or better: just setup SSH and expose a port differently
            # For simplicity, let's use docker exec to setup SSH, then it won't need port mapping
            # Actually, we need to expose port 22 when creating the container
            # Let's stop and recreate with the port exposed
            logger.debug("Container doesn't expose SSH port, recreating with port exposed...")
            self._run_docker_command(["rm", "-f", container_name])

            # Recreate with explicit port mapping
            docker_args = [
                "run",
                "-d",
                "--name",
                container_name,
                "-p",
                f"{CONTAINER_SSH_PORT}",  # Map container port 22 to random host port
            ]

            if config.cpu is not None:
                docker_args.extend(["--cpus", str(config.cpu)])
            if config.memory is not None:
                memory_mb = int(config.memory * 1024)
                docker_args.extend(["--memory", f"{memory_mb}m"])

            for key, value in container_labels.items():
                docker_args.extend(["--label", f"{key}={value}"])

            docker_args.extend([base_image, "sleep", "infinity"])
            self._run_docker_command(docker_args)

            ssh_port = self._get_container_port_mapping(container_name)
            if ssh_port is None:
                raise MngrError("Failed to get SSH port mapping for container")

        logger.debug("SSH port mapping: localhost:{}", ssh_port)

        # Set up SSH in the container
        logger.debug("Setting up SSH in container...")
        self._setup_ssh_in_container(container_name, client_public_key, host_private_key, host_public_key)

        # Update the container labels with the actual SSH port
        # Since Docker labels are immutable, we need to store the port info elsewhere or recreate
        # For now, we'll store the actual port in our local data file
        host_data_dir = self._get_host_data_dir(host_id)
        host_data_dir.mkdir(parents=True, exist_ok=True)
        (host_data_dir / "ssh_port").write_text(str(ssh_port))

        # Add host to known_hosts
        logger.debug("Adding host to known_hosts: localhost:{}", ssh_port)
        add_host_to_known_hosts(self._known_hosts_path, "localhost", ssh_port, host_public_key)

        # Wait for sshd to be ready
        logger.debug("Waiting for sshd to be ready...")
        self._wait_for_sshd("localhost", ssh_port)
        logger.debug("sshd is ready")

        # Save user tags if provided
        if tags:
            self._save_tags(host_id, dict(tags))

        # Create pyinfra host
        pyinfra_host = self._create_pyinfra_host("localhost", ssh_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        # Create and return the Host object
        host = Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

        logger.info("Docker host created: id={}, name={}, ssh=localhost:{}", host_id, name, ssh_port)
        return host

    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Stop a Docker container."""
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.info("Stopping Docker container: {}", host_id)

        container_info = self._find_container_by_host_id(host_id)
        if container_info:
            container_name = container_info.get("Names", "")
            if container_name:
                try:
                    self._run_docker_command(["stop", container_name])
                except MngrError as e:
                    logger.warning("Error stopping container: {}", e)
        else:
            logger.debug("No container found with host_id={}", host_id)

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        """Start a stopped container."""
        host_id = host.id if isinstance(host, HostInterface) else host

        container_info = self._find_container_by_host_id(host_id)
        if container_info is None:
            raise HostNotFoundError(host_id)

        container_name = container_info.get("Names", "")
        if not container_name:
            raise HostNotFoundError(host_id)

        # Start the container if not running
        if not self._is_container_running(container_name):
            logger.info("Starting container: {}", container_name)
            self._run_docker_command(["start", container_name])

            # Restart sshd in the container (it may have stopped)
            self._docker_exec(container_name, ["sh", "-c", "/usr/sbin/sshd"], check=False)

        # Get the SSH port
        ssh_port = self._get_container_port_mapping(container_name)
        if ssh_port is None:
            # Try to read from local data
            port_file = self._get_host_data_dir(host_id) / "ssh_port"
            if port_file.exists():
                ssh_port = int(port_file.read_text().strip())

        if ssh_port is None:
            raise MngrError(f"Cannot determine SSH port for container {container_name}")

        # Get SSH keys
        private_key_path, _ = self._get_ssh_keypair()
        _, host_public_key = self._get_host_keypair()

        # Add to known hosts
        add_host_to_known_hosts(self._known_hosts_path, "localhost", ssh_port, host_public_key)

        # Wait for sshd
        self._wait_for_sshd("localhost", ssh_port)

        # Create pyinfra host
        pyinfra_host = self._create_pyinfra_host("localhost", ssh_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        return Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        """Destroy a Docker container permanently."""
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.info("Destroying Docker container: {}", host_id)

        container_info = self._find_container_by_host_id(host_id)
        if container_info:
            container_name = container_info.get("Names", "")
            if container_name:
                try:
                    self._run_docker_command(["rm", "-f", container_name])
                except MngrError as e:
                    logger.warning("Error removing container: {}", e)

        # Delete local data
        self._delete_host_data(host_id)

    # =========================================================================
    # Discovery Methods
    # =========================================================================

    def get_host(
        self,
        host: HostId | HostName,
    ) -> Host:
        """Get a host by ID or name."""
        if isinstance(host, HostId):
            container_info = self._find_container_by_host_id(host)
            if container_info is None:
                raise HostNotFoundError(host)

            container_name = container_info.get("Names", "")
            if not container_name:
                raise HostNotFoundError(host)

            labels = self._get_container_labels(container_name)
            host_id, name, _, host_public_key, config = self._parse_container_labels(labels)

            if not self._is_container_running(container_name):
                raise HostNotFoundError(host)

            ssh_port = self._get_container_port_mapping(container_name)
            if ssh_port is None:
                port_file = self._get_host_data_dir(host_id) / "ssh_port"
                if port_file.exists():
                    ssh_port = int(port_file.read_text().strip())

            if ssh_port is None or host_public_key is None:
                raise HostNotFoundError(host)

            add_host_to_known_hosts(self._known_hosts_path, "localhost", ssh_port, host_public_key)

            private_key_path, _ = self._get_ssh_keypair()
            pyinfra_host = self._create_pyinfra_host("localhost", ssh_port, private_key_path)
            connector = PyinfraConnector(pyinfra_host)

            return Host(
                id=host_id,
                connector=connector,
                provider_instance=self,
                mngr_ctx=self.mngr_ctx,
            )

        # If it's a HostName, search by name
        container_info = self._find_container_by_name(host)
        if container_info is None:
            raise HostNotFoundError(host)

        container_name = container_info.get("Names", "")
        if not container_name:
            raise HostNotFoundError(host)

        labels = self._get_container_labels(container_name)
        host_id, name, _, host_public_key, config = self._parse_container_labels(labels)

        if not self._is_container_running(container_name):
            raise HostNotFoundError(host)

        ssh_port = self._get_container_port_mapping(container_name)
        if ssh_port is None:
            port_file = self._get_host_data_dir(host_id) / "ssh_port"
            if port_file.exists():
                ssh_port = int(port_file.read_text().strip())

        if ssh_port is None or host_public_key is None:
            raise HostNotFoundError(host)

        add_host_to_known_hosts(self._known_hosts_path, "localhost", ssh_port, host_public_key)

        private_key_path, _ = self._get_ssh_keypair()
        pyinfra_host = self._create_pyinfra_host("localhost", ssh_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        return Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

    def list_hosts(
        self,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List all active Docker container hosts."""
        hosts: list[HostInterface] = []
        for container_info in self._list_mngr_containers():
            try:
                host_obj = self._create_host_from_container(container_info)
                if host_obj is not None:
                    hosts.append(host_obj)
            except (KeyError, ValueError) as e:
                logger.debug("Skipping container with invalid labels: {}", e)
                continue
        return hosts

    def get_host_resources(self, host: HostInterface) -> HostResources:
        """Get resource information for a Docker container."""
        container_info = self._find_container_by_host_id(host.id)
        if container_info is None:
            return HostResources(
                cpu=CpuResources(count=1, frequency_ghz=None),
                memory_gb=1.0,
                disk_gb=None,
                gpu=None,
            )

        container_name = container_info.get("Names", "")
        if not container_name:
            return HostResources(
                cpu=CpuResources(count=1, frequency_ghz=None),
                memory_gb=1.0,
                disk_gb=None,
                gpu=None,
            )

        labels = self._get_container_labels(container_name)
        host_record_json = labels.get(LABEL_HOST_RECORD)
        if not host_record_json:
            return HostResources(
                cpu=CpuResources(count=1, frequency_ghz=None),
                memory_gb=1.0,
                disk_gb=None,
                gpu=None,
            )

        host_record = json.loads(host_record_json)
        config_data = host_record.get("config", {})
        cpu = config_data.get("cpu")
        memory = config_data.get("memory")

        return HostResources(
            cpu=CpuResources(count=max(1, int(cpu)) if cpu else 1, frequency_ghz=None),
            memory_gb=memory if memory else 1.0,
            disk_gb=None,
            gpu=None,
        )

    # =========================================================================
    # Snapshot Methods (not supported)
    # =========================================================================

    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        """Create a snapshot. Not supported for Docker provider."""
        raise NotImplementedError("Docker provider does not support snapshots")

    def list_snapshots(
        self,
        host: HostInterface | HostId,
    ) -> list[SnapshotInfo]:
        """List snapshots. Returns empty list as snapshots are not supported."""
        return []

    def delete_snapshot(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId,
    ) -> None:
        """Delete a snapshot. Not supported for Docker provider."""
        raise SnapshotNotFoundError(snapshot_id)

    # =========================================================================
    # Volume Methods (not supported)
    # =========================================================================

    def list_volumes(self) -> list[VolumeInfo]:
        """List volumes. Returns empty list as volumes are not supported."""
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        """Delete a volume. Not supported for Docker provider."""
        raise NotImplementedError("Docker provider does not support volumes")

    # =========================================================================
    # Host Mutation Methods
    # =========================================================================

    def get_host_tags(
        self,
        host: HostInterface | HostId,
    ) -> dict[str, str]:
        """Get user-defined tags for a host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        return self._load_tags(host_id)

    def set_host_tags(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Replace all user-defined tags on a host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        self._save_tags(host_id, dict(tags))

    def add_tags_to_host(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Add or update tags on a host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        existing_tags = self._load_tags(host_id)
        existing_tags.update(tags)
        self._save_tags(host_id, existing_tags)

    def remove_tags_from_host(
        self,
        host: HostInterface | HostId,
        keys: Sequence[str],
    ) -> None:
        """Remove tags from a host by key."""
        host_id = host.id if isinstance(host, HostInterface) else host
        existing_tags = self._load_tags(host_id)
        for key in keys:
            existing_tags.pop(key, None)
        self._save_tags(host_id, existing_tags)

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> Host:
        """Rename a host. Docker containers cannot be renamed, so this is a no-op."""
        # Docker containers can actually be renamed, but the label stays the same
        # For simplicity, we just return the host as-is
        host_id = host.id if isinstance(host, HostInterface) else host
        return self.get_host(host_id)

    # =========================================================================
    # Connector Method
    # =========================================================================

    def get_connector(
        self,
        host: HostInterface | HostId,
    ) -> PyinfraHost:
        """Get a pyinfra connector for the host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        container_info = self._find_container_by_host_id(host_id)
        if container_info is None:
            raise HostNotFoundError(host_id)

        container_name = container_info.get("Names", "")
        if not container_name:
            raise HostNotFoundError(host_id)

        labels = self._get_container_labels(container_name)
        _, _, _, host_public_key, _ = self._parse_container_labels(labels)

        ssh_port = self._get_container_port_mapping(container_name)
        if ssh_port is None:
            port_file = self._get_host_data_dir(host_id) / "ssh_port"
            if port_file.exists():
                ssh_port = int(port_file.read_text().strip())

        if ssh_port is None:
            raise HostNotFoundError(host_id)

        if host_public_key is not None:
            add_host_to_known_hosts(self._known_hosts_path, "localhost", ssh_port, host_public_key)

        private_key_path, _ = self._get_ssh_keypair()
        return self._create_pyinfra_host("localhost", ssh_port, private_key_path)

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    def close(self) -> None:
        """Clean up resources. Docker provider doesn't need special cleanup."""
        pass
