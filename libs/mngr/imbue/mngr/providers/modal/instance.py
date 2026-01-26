"""Modal provider instance implementation.

Manages Modal sandboxes as hosts with SSH access via pyinfra.

Host metadata (SSH info, config, snapshots) is stored on a Modal Volume rather
than in sandbox tags. This allows multiple mngr instances to share state and
enables restoration from snapshots even after the original sandbox is gone.
Only host_id and host_name are stored as sandbox tags for discovery purposes.
"""

import argparse
import io
import os
import socket
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from functools import wraps
from pathlib import Path
from typing import Final
from typing import Mapping
from typing import ParamSpec
from typing import Sequence
from typing import TypeVar
from typing import cast

import modal
import modal.exception
from dockerfile_parse import DockerfileParser
from loguru import logger
from pydantic import ConfigDict
from pydantic import Field
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State as PyinfraState
from pyinfra.api.inventory import Inventory
from pyinfra.connectors.sshuserclient.client import get_host_keys

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ModalAuthError
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
from imbue.mngr.providers.modal.config import ModalProviderConfig
from imbue.mngr.providers.modal.ssh_utils import add_host_to_known_hosts
from imbue.mngr.providers.modal.ssh_utils import load_or_create_host_keypair
from imbue.mngr.providers.modal.ssh_utils import load_or_create_ssh_keypair
from imbue.mngr.providers.ssh_host_setup import build_check_and_install_packages_command
from imbue.mngr.providers.ssh_host_setup import build_configure_ssh_command
from imbue.mngr.providers.ssh_host_setup import parse_warnings_from_output

# Constants
CONTAINER_SSH_PORT = 22
# 2 minutes default sandbox lifetime (so that we don't just leave tons of them running--we're not doing a good job of cleaning them up yet)
DEFAULT_SANDBOX_TIMEOUT = 2 * 60
# Seconds to wait for sshd to be ready
SSH_CONNECT_TIMEOUT = 60

# Tag key constants for sandbox metadata stored in Modal tags.
# Only host_id and host_name are stored as tags (for discovery). All other
# metadata is stored on the Modal Volume for persistence and sharing.
TAG_HOST_ID: Final[str] = "mngr_host_id"
TAG_HOST_NAME: Final[str] = "mngr_host_name"
TAG_USER_PREFIX: Final[str] = "mngr_user_"

P = ParamSpec("P")
T = TypeVar("T")


def build_sandbox_tags(
    host_id: HostId,
    name: HostName,
    user_tags: Mapping[str, str] | None,
) -> dict[str, str]:
    """Build the tags dict to store on a Modal sandbox.

    Only stores host_id, host_name, and user tags. All other metadata
    (SSH info, config, snapshots) is stored on the Modal Volume.
    """
    tags: dict[str, str] = {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }

    # Store user tags with a prefix to separate them from mngr tags
    if user_tags:
        for key, value in user_tags.items():
            tags[TAG_USER_PREFIX + key] = value

    return tags


def parse_sandbox_tags(
    tags: dict[str, str],
) -> tuple[HostId, HostName, dict[str, str]]:
    """Parse tags from a Modal sandbox into structured data.

    Returns (host_id, name, user_tags). All other metadata is read from the volume.
    """
    host_id = HostId(tags[TAG_HOST_ID])
    name = HostName(tags[TAG_HOST_NAME])

    # Extract user tags (those with the user prefix)
    user_tags: dict[str, str] = {}
    for key, value in tags.items():
        if key.startswith(TAG_USER_PREFIX):
            user_key = key[len(TAG_USER_PREFIX) :]
            user_tags[user_key] = value

    return host_id, name, user_tags


def handle_modal_auth_error(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to convert modal.exception.AuthError to ModalAuthError.

    Wraps provider methods to catch Modal authentication errors at the boundary
    and convert them to our ModalAuthError with a helpful message.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except modal.exception.AuthError as e:
            raise ModalAuthError() from e

    return wrapper


class SandboxConfig(FrozenModel):
    """Configuration parsed from build arguments."""

    gpu: str | None = None
    cpu: float = 1.0
    memory: float = 1.0
    image: str | None = None
    dockerfile: str | None = None
    timeout: int = DEFAULT_SANDBOX_TIMEOUT
    region: str | None = None
    context_dir: str | None = None
    secrets: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Environment variable names to pass as secrets during image build",
    )


class SnapshotRecord(FrozenModel):
    """Snapshot metadata stored in the host record on the volume."""

    id: str = Field(description="Unique identifier for the snapshot")
    name: str = Field(description="Human-readable name")
    created_at: str = Field(description="ISO format timestamp")
    modal_image_id: str = Field(description="Modal image ID for restoration")


class HostRecord(FrozenModel):
    """Host metadata stored on the Modal Volume.

    This record contains all information needed to connect to and restore a host.
    It is stored at /<host_id>.json on the volume.
    """

    host_id: str = Field(description="Unique identifier for the host")
    host_name: str = Field(description="Human-readable name")
    ssh_host: str = Field(description="SSH hostname for connecting to the sandbox")
    ssh_port: int = Field(description="SSH port number")
    ssh_host_public_key: str = Field(description="SSH host public key for verification")
    config: SandboxConfig = Field(description="Sandbox configuration")
    user_tags: dict[str, str] = Field(default_factory=dict, description="User-defined tags")
    snapshots: list[SnapshotRecord] = Field(default_factory=list, description="List of snapshots")


class ModalProviderApp(FrozenModel):
    """Encapsulates a Modal app and its associated resources.

    This class manages the lifecycle of a Modal app, including:
    - The Modal app itself and its run context
    - Output capture for detecting build failures
    - The state volume for persisting host records

    Instances are created by ModalProviderBackend and passed to ModalProviderInstance.
    Multiple ModalProviderInstance objects can share the same ModalProviderApp if they
    use the same app_name.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    app_name: str = Field(frozen=True, description="The name of the Modal app")
    app: modal.App = Field(frozen=True, description="The Modal app instance")
    volume: modal.Volume = Field(frozen=True, description="The Modal volume for state storage")
    close_callback: Callable[[], None] = Field(frozen=True, description="Callback to clean up the app context")
    get_output_callback: Callable[[], str] = Field(frozen=True, description="Callback to get the log output buffer")

    def get_captured_output(self) -> str:
        """Get all captured Modal output.

        Returns the contents of the output buffer that has been capturing Modal
        logs since the app was created. This can be used to detect build failures
        or other issues by inspecting the captured output.
        """
        return self.get_output_callback()

    def close(self) -> None:
        self.close_callback()


class ModalProviderInstance(BaseProviderInstance):
    """Provider instance for managing Modal sandboxes as hosts.

    Each sandbox runs sshd and is accessed via pyinfra's SSH connector.
    Sandboxes have a maximum lifetime (timeout) after which they are automatically
    terminated by Modal.

    Host metadata (SSH info, config, snapshots) is stored on a Modal Volume
    for persistence and sharing between mngr instances. Only host_id, host_name,
    and user tags are stored as sandbox tags for discovery via Sandbox.list().
    """

    config: ModalProviderConfig = Field(frozen=True, description="Modal provider configuration")
    modal_app: ModalProviderApp = Field(frozen=True, description="Modal app manager")

    @property
    def supports_snapshots(self) -> bool:
        return True

    @property
    def supports_volumes(self) -> bool:
        return False

    @property
    def supports_mutable_tags(self) -> bool:
        return True

    @property
    def app_name(self) -> str:
        """Get the Modal app name from the modal_app manager."""
        return self.modal_app.app_name

    @property
    def _keys_dir(self) -> Path:
        config_dir = self.mngr_ctx.config.default_host_dir.expanduser()
        return config_dir / "providers" / "modal"

    def _get_ssh_keypair(self) -> tuple[Path, str]:
        """Get or create the SSH keypair for this provider instance."""
        return load_or_create_ssh_keypair(self._keys_dir)

    def _get_host_keypair(self) -> tuple[Path, str]:
        """Get or create the SSH host keypair for Modal sandboxes.

        This key is used as the SSH host key for all sandboxes, allowing us to
        pre-trust the key and avoid host key verification prompts.
        """
        return load_or_create_host_keypair(self._keys_dir)

    @property
    def _known_hosts_path(self) -> Path:
        """Get the path to the known_hosts file for this provider instance."""
        return self._keys_dir / "known_hosts"

    # =========================================================================
    # Volume-based Host Record Methods
    # =========================================================================

    def _get_volume(self) -> modal.Volume:
        """Get the Modal volume for state storage.

        The volume is used to persist host records (including snapshots) across
        sandbox termination. This allows multiple mngr instances to share state.
        """
        return self.modal_app.volume

    def _get_host_record_path(self, host_id: HostId) -> str:
        """Get the path for a host record on the volume."""
        return f"/{host_id}.json"

    def _write_host_record(self, host_record: HostRecord) -> None:
        """Write a host record to the volume."""
        volume = self._get_volume()
        path = self._get_host_record_path(HostId(host_record.host_id))
        data = host_record.model_dump_json(indent=2)
        logger.trace("Writing host record to volume: {}", path)

        # Upload the data as a file-like object
        with volume.batch_upload(force=True) as batch:
            batch.put_file(io.BytesIO(data.encode("utf-8")), path)

    def _read_host_record(self, host_id: HostId) -> HostRecord | None:
        """Read a host record from the volume.

        Returns None if the host record doesn't exist.
        """
        volume = self._get_volume()
        path = self._get_host_record_path(host_id)
        logger.trace("Reading host record from volume: {}", path)

        try:
            # Read file returns a generator that yields bytes chunks
            chunks: list[bytes] = []
            for chunk in volume.read_file(path):
                chunks.append(chunk)
            data = b"".join(chunks)
            return HostRecord.model_validate_json(data)
        except FileNotFoundError:
            return None

    def _delete_host_record(self, host_id: HostId) -> None:
        """Delete a host record from the volume."""
        volume = self._get_volume()
        path = self._get_host_record_path(host_id)
        logger.trace("Deleting host record from volume: {}", path)

        try:
            volume.remove_file(path)
        except FileNotFoundError:
            pass

    def _build_modal_image(
        self,
        base_image: str | None = None,
        dockerfile: Path | None = None,
        context_dir: Path | None = None,
        secrets: Sequence[str] = (),
    ) -> modal.Image:
        """Build a Modal image.

        If dockerfile is provided, builds from that Dockerfile with per-layer caching.
        Each instruction is applied separately, so if a build fails at step N,
        steps 1 through N-1 are cached and don't need to be re-run.

        Elif base_image is provided (e.g., "python:3.11-slim"), uses that as the
        base. Otherwise uses debian:bookworm-slim.

        The context_dir specifies the directory for Dockerfile COPY/ADD instructions.
        If not provided, defaults to the Dockerfile's parent directory.

        The secrets parameter is a sequence of environment variable names whose values
        will be read from the current environment and passed to the Modal image build
        process. These are available during Dockerfile RUN commands via --mount=type=secret.

        SSH and tmux setup is handled at runtime in _start_sshd_in_sandbox to
        allow warning if these tools are not pre-installed in the base image.
        """
        # Build modal secrets from environment variables
        modal_secrets = _build_modal_secrets_from_env(secrets)

        if dockerfile is not None:
            dockerfile_contents = dockerfile.read_text()
            effective_context_dir = context_dir if context_dir is not None else dockerfile.parent
            image = _build_image_from_dockerfile_contents(
                dockerfile_contents,
                context_dir=effective_context_dir,
                is_each_layer_cached=True,
                secrets=modal_secrets,
            )
        elif base_image:
            image = modal.Image.from_registry(base_image)
        else:
            image = modal.Image.debian_slim()

        return image

    def _check_and_install_packages(
        self,
        sandbox: modal.Sandbox,
    ) -> None:
        """Check for required packages and install if missing, with warnings.

        Uses a single shell command to check for all packages and install missing ones,
        which is faster than multiple exec calls and allows the logic to be reused
        by other providers.

        Checks for sshd, tmux, curl, rsync, and git. If any is missing, logs a warning
        and installs via apt. This allows users to pre-configure their base images
        for faster startup while supporting images without these tools.
        """
        # Build and execute the combined check-and-install command
        check_install_cmd = build_check_and_install_packages_command(str(self.host_dir))
        process = sandbox.exec("sh", "-c", check_install_cmd)

        # Read output (implicitly waits for completion)
        stdout = process.stdout.read()

        # Parse warnings from output and log them
        warnings = parse_warnings_from_output(stdout)
        for warning in warnings:
            logger.warning(warning)

    def _start_sshd_in_sandbox(
        self,
        sandbox: modal.Sandbox,
        client_public_key: str,
        host_private_key: str,
        host_public_key: str,
        ssh_user: str = "root",
    ) -> None:
        """Set up SSH access and start sshd in the sandbox.

        This method handles the complete SSH setup including package installation
        (if needed), key configuration, and starting the sshd daemon.

        All setup (except starting sshd) is done via a single shell command for
        speed and to allow reuse by other providers.
        """
        # Check for required packages and install if missing
        self._check_and_install_packages(sandbox)

        logger.debug("Configuring SSH keys in sandbox for user={}", ssh_user)

        # Build and execute the SSH configuration command
        configure_ssh_cmd = build_configure_ssh_command(
            user=ssh_user,
            client_public_key=client_public_key,
            host_private_key=host_private_key,
            host_public_key=host_public_key,
        )
        sandbox.exec("sh", "-c", configure_ssh_cmd).wait()

        logger.debug("Starting sshd in sandbox")

        # Start sshd (-D: don't detach, -e: print errors to stdout)
        sandbox.exec("/usr/sbin/sshd", "-D", "-e")

    def _get_ssh_info_from_sandbox(self, sandbox: modal.Sandbox) -> tuple[str, int]:
        """Extract SSH connection info from a running sandbox."""
        tunnels = sandbox.tunnels()
        ssh_tunnel = tunnels[CONTAINER_SSH_PORT]
        return ssh_tunnel.tcp_socket

    def _wait_for_sshd(self, hostname: str, port: int, timeout_seconds: float = SSH_CONNECT_TIMEOUT) -> None:
        """Wait for sshd to be ready to accept connections.

        Uses socket timeouts to pace connection attempts without explicit sleep calls.
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Socket timeout provides delay between connection attempts
                sock.settimeout(2.0)
                sock.connect((hostname, port))
                banner = sock.recv(256)
                if banner.startswith(b"SSH-"):
                    return
            except (socket.error, socket.timeout):
                # Connection failed or timed out, will retry
                pass
            finally:
                sock.close()
        raise MngrError(f"SSH server not ready after {timeout_seconds}s at {hostname}:{port}")

    def _create_pyinfra_host(self, hostname: str, port: int, private_key_path: Path) -> PyinfraHost:
        """Create a pyinfra host with SSH connector."""
        # Clear pyinfra's memoized known_hosts cache to ensure fresh reads.
        # pyinfra caches known_hosts by filename, but we add new entries dynamically,
        # so we need to clear the cache to pick up new entries.
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

    def _setup_sandbox_ssh_and_create_host(
        self,
        sandbox: modal.Sandbox,
        host_id: HostId,
        host_name: HostName,
        user_tags: Mapping[str, str] | None,
    ) -> tuple[Host, str, int, str]:
        """Set up SSH in a sandbox and create a Host object.

        This helper consolidates the common logic for setting up SSH access
        after a sandbox is created, used by both create_host and start_host.

        Returns a tuple of (Host, ssh_host, ssh_port, host_public_key) so callers
        can use the SSH info for creating/updating host records.
        """
        # Get SSH keypairs
        private_key_path, client_public_key = self._get_ssh_keypair()
        host_key_path, host_public_key = self._get_host_keypair()
        host_private_key = host_key_path.read_text()

        # Start sshd with our host key
        self._start_sshd_in_sandbox(sandbox, client_public_key, host_private_key, host_public_key)

        # Get SSH connection info
        ssh_host, ssh_port = self._get_ssh_info_from_sandbox(sandbox)
        logger.debug("SSH endpoint: {}:{}", ssh_host, ssh_port)

        # Add the host to our known_hosts file before waiting for sshd
        logger.debug("Adding host to known_hosts: {}:{}", ssh_host, ssh_port)
        add_host_to_known_hosts(self._known_hosts_path, ssh_host, ssh_port, host_public_key)

        # Wait for sshd to be ready
        logger.debug("Waiting for sshd to be ready...")
        self._wait_for_sshd(ssh_host, ssh_port)
        logger.debug("sshd is ready")

        # Set sandbox tags
        sandbox_tags = self._build_sandbox_tags(
            host_id=host_id,
            name=host_name,
            user_tags=user_tags,
        )
        logger.debug("Setting sandbox tags: {}", list(sandbox_tags.keys()))
        sandbox.set_tags(sandbox_tags)

        # Create pyinfra host and connector
        pyinfra_host = self._create_pyinfra_host(ssh_host, ssh_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        # Create the Host object
        host = Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

        return host, ssh_host, ssh_port, host_public_key

    def _parse_build_args(
        self,
        build_args: Sequence[str] | None,
    ) -> SandboxConfig:
        """Parse build arguments into sandbox configuration.

        Accepts arguments in two formats:
        - Key-value: gpu=h100, cpu=2, memory=4
        - Flag style: --gpu=h100, --gpu h100

        Both formats can be mixed. Unknown arguments raise an error.
        """
        if not build_args:
            return SandboxConfig(
                gpu=None,
                cpu=self.config.default_cpu,
                memory=self.config.default_memory,
                image=None,
                dockerfile=None,
                timeout=self.config.default_timeout,
                region=None,
                context_dir=None,
                secrets=(),
            )

        # Normalize arguments: convert "key=value" to "--key=value"
        normalized_args: list[str] = []
        for arg in build_args:
            if "=" in arg and not arg.startswith("-"):
                # Simple key=value format, convert to --key=value
                normalized_args.append(f"--{arg}")
            else:
                normalized_args.append(arg)

        # Use argparse for robust parsing
        parser = argparse.ArgumentParser(
            prog="build_args",
            add_help=False,
            exit_on_error=False,
        )
        parser.add_argument("--gpu", type=str, default=None)
        parser.add_argument("--cpu", type=float, default=self.config.default_cpu)
        parser.add_argument("--memory", type=float, default=self.config.default_memory)
        parser.add_argument("--image", type=str, default=None)
        parser.add_argument("--dockerfile", type=str, default=None)
        parser.add_argument("--timeout", type=int, default=self.config.default_timeout)
        parser.add_argument("--region", type=str, default=None)
        parser.add_argument("--context-dir", type=str, default=None)
        parser.add_argument("--secret", type=str, action="append", default=[])

        try:
            parsed, unknown = parser.parse_known_args(normalized_args)
        except argparse.ArgumentError as e:
            raise MngrError(f"Invalid build argument: {e}") from None

        if unknown:
            raise MngrError(f"Unknown build arguments: {unknown}")

        return SandboxConfig(
            gpu=parsed.gpu,
            cpu=parsed.cpu,
            memory=parsed.memory,
            image=parsed.image,
            dockerfile=parsed.dockerfile,
            timeout=parsed.timeout,
            region=parsed.region,
            context_dir=parsed.context_dir,
            secrets=tuple(parsed.secret),
        )

    # =========================================================================
    # Tag Management Helpers
    # =========================================================================

    def _build_sandbox_tags(
        self,
        host_id: HostId,
        name: HostName,
        user_tags: Mapping[str, str] | None,
    ) -> dict[str, str]:
        """Build the tags dict to store on a Modal sandbox."""
        return build_sandbox_tags(host_id, name, user_tags)

    def _parse_sandbox_tags(
        self,
        tags: dict[str, str],
    ) -> tuple[HostId, HostName, dict[str, str]]:
        """Parse tags from a Modal sandbox into structured data."""
        return parse_sandbox_tags(tags)

    def _get_modal_app(self) -> modal.App:
        """Get or create the Modal app for this provider instance.

        The app is lazily created by the modal_app manager when first needed.
        This allows basic property tests to run without Modal credentials.

        Modal output is captured at the modal_app level.

        Raises modal.exception.AuthError if Modal credentials are not configured.
        """
        return self.modal_app.app

    def get_captured_output(self) -> str:
        """Get all captured Modal output for this provider instance.

        Returns the contents of the output buffer that has been capturing Modal
        logs since the app was created. This can be used to detect build failures
        or other issues by inspecting the captured output.

        Returns an empty string if no app has been created yet.
        """
        return self.modal_app.get_captured_output()

    def _find_sandbox_by_host_id(self, host_id: HostId) -> modal.Sandbox | None:
        """Find a Modal sandbox by its mngr host_id tag."""
        logger.trace("Looking up sandbox with host_id={}", host_id)
        app = self._get_modal_app()
        for sandbox in modal.Sandbox.list(app_id=app.app_id, tags={TAG_HOST_ID: str(host_id)}):
            return sandbox
        return None

    def _find_sandbox_by_name(self, name: HostName) -> modal.Sandbox | None:
        """Find a Modal sandbox by its mngr host_name tag."""
        logger.trace("Looking up sandbox with name={}", name)
        app = self._get_modal_app()
        for sandbox in modal.Sandbox.list(app_id=app.app_id, tags={TAG_HOST_NAME: str(name)}):
            return sandbox
        return None

    def _list_sandboxes(self) -> list[modal.Sandbox]:
        """List all Modal sandboxes managed by this mngr provider instance."""
        logger.trace("Listing all mngr sandboxes for app={}", self.app_name)
        app = self._get_modal_app()
        sandboxes: list[modal.Sandbox] = []
        for sandbox in modal.Sandbox.list(app_id=app.app_id):
            tags = sandbox.get_tags()
            if TAG_HOST_ID in tags:
                sandboxes.append(sandbox)
        return sandboxes

    def _create_host_from_sandbox(
        self,
        sandbox: modal.Sandbox,
    ) -> Host | None:
        """Create a Host object from a Modal sandbox.

        This reads host metadata from the volume and adds the host key to
        known_hosts for the sandbox's SSH endpoint, enabling SSH connections
        to succeed without host key verification prompts.

        Returns None if the host record doesn't exist on the volume.
        """
        tags = sandbox.get_tags()
        host_id, name, user_tags = self._parse_sandbox_tags(tags)

        # Read host metadata from the volume
        host_record = self._read_host_record(host_id)
        if host_record is None:
            logger.debug("Skipping sandbox {} - no host record on volume", sandbox.object_id)
            return None

        # Add the sandbox's host key to known_hosts so SSH connections will work
        add_host_to_known_hosts(
            self._known_hosts_path,
            host_record.ssh_host,
            host_record.ssh_port,
            host_record.ssh_host_public_key,
        )

        private_key_path, _ = self._get_ssh_keypair()
        pyinfra_host = self._create_pyinfra_host(
            host_record.ssh_host,
            host_record.ssh_port,
            private_key_path,
        )
        connector = PyinfraConnector(pyinfra_host)

        return Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

    # =========================================================================
    # Core Lifecycle Methods
    # =========================================================================

    @handle_modal_auth_error
    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
    ) -> Host:
        """Create a new Modal sandbox host."""
        # Generate host ID
        host_id = HostId.generate()

        logger.info("Creating host {} in {} ...", name, self.name)
        logger.debug("Creating host: name={} id={} provider=modal", name, host_id)

        # Parse build arguments (including --dockerfile if specified)
        config = self._parse_build_args(build_args)
        base_image = str(image) if image else config.image
        dockerfile_path = Path(config.dockerfile) if config.dockerfile else None
        context_dir_path = Path(config.context_dir) if config.context_dir else None

        # Build the Modal image
        logger.debug("Building Modal image...")
        modal_image = self._build_modal_image(base_image, dockerfile_path, context_dir_path, config.secrets)

        # Get or create the Modal app (uses singleton pattern with context manager)
        logger.debug("Getting Modal app: {}", self.app_name)
        app = self._get_modal_app()

        # Create the sandbox
        logger.debug(
            "Creating Modal sandbox with timeout={}s, cpu={}, memory={}GB",
            config.timeout,
            config.cpu,
            config.memory,
        )

        # Memory is in GB but Modal expects MB
        memory_mb = int(config.memory * 1024)
        try:
            sandbox = modal.Sandbox.create(
                image=modal_image,
                app=app,
                timeout=config.timeout,
                cpu=config.cpu,
                memory=memory_mb,
                unencrypted_ports=[CONTAINER_SSH_PORT],
                gpu=config.gpu,
                region=config.region,
            )
        except modal.exception.RemoteError as e:
            raise MngrError(f"Failed to create Modal sandbox: {e}\n{self.get_captured_output()}") from None
        logger.debug("Created Modal sandbox: id={}", sandbox.object_id)

        # Set up SSH and create host object using shared helper
        host, ssh_host, ssh_port, host_public_key = self._setup_sandbox_ssh_and_create_host(
            sandbox=sandbox,
            host_id=host_id,
            host_name=name,
            user_tags=tags,
        )

        # Store full host metadata on the volume for persistence
        host_record = HostRecord(
            host_id=str(host_id),
            host_name=str(name),
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_host_public_key=host_public_key,
            config=config,
            user_tags=dict(tags) if tags else {},
            snapshots=[],
        )
        logger.debug("Writing host record to volume for host_id={}", host_id)
        self._write_host_record(host_record)

        logger.debug("Modal host created: id={}, name={}, ssh={}:{}", host_id, name, ssh_host, ssh_port)
        return host

    @handle_modal_auth_error
    def stop_host(
        self,
        host: HostInterface | HostId,
        create_snapshot: bool = True,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Stop a Modal sandbox.

        Note: Modal sandboxes cannot be stopped and resumed - they can only be
        terminated. This method terminates the sandbox.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.info("Stopping (terminating) Modal sandbox: {}", host_id)

        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox:
            try:
                sandbox.terminate()
            except modal.exception.Error as e:
                logger.warning("Error terminating sandbox: {}", e)
        else:
            logger.debug("No sandbox found with host_id={}, may already be terminated", host_id)

    @handle_modal_auth_error
    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        """Start a stopped host, optionally restoring from a snapshot.

        If the sandbox is still running, returns the existing host. If the
        sandbox has been terminated and a snapshot_id is provided, creates
        a new sandbox from the snapshot image. Without a snapshot_id, a
        terminated sandbox cannot be restarted.
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # If sandbox is still running, return it
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            host_obj = self._create_host_from_sandbox(sandbox)
            if host_obj is not None:
                if snapshot_id is not None:
                    logger.warning(
                        "Sandbox {} is still running; ignoring snapshot_id parameter. "
                        "Stop the host first to restore from a snapshot.",
                        host_id,
                    )
                return host_obj

        # Sandbox is not running - try to restore from snapshot if provided
        if snapshot_id is None:
            raise MngrError(
                f"Modal sandbox {host_id} is not running and cannot be restarted. "
                "Provide a snapshot_id to restore from a snapshot, or create a new host."
            )

        # Load host record from volume
        host_record = self._read_host_record(host_id)
        if host_record is None:
            raise HostNotFoundError(host_id)

        # Find the snapshot in the host record
        snapshot_data: SnapshotRecord | None = None
        for snap in host_record.snapshots:
            if snap.id == str(snapshot_id):
                snapshot_data = snap
                break

        if snapshot_data is None:
            raise SnapshotNotFoundError(snapshot_id)

        modal_image_id = snapshot_data.modal_image_id
        if not modal_image_id:
            raise MngrError(f"Snapshot {snapshot_id} does not contain a Modal image ID for restoration.")

        logger.info("Restoring Modal sandbox from snapshot: host_id={}, snapshot_id={}", host_id, snapshot_id)

        # Use configuration from host record
        config = host_record.config
        host_name = HostName(host_record.host_name)
        user_tags = host_record.user_tags

        # Create the image reference from the snapshot
        logger.debug("Creating sandbox from snapshot image: {}", modal_image_id)
        # Cast needed because modal.Image.from_id returns Self which the type checker can't resolve
        modal_image = cast(modal.Image, modal.Image.from_id(modal_image_id))

        # Get or create the Modal app
        app = self._get_modal_app()

        # Create the sandbox from the snapshot image
        memory_mb = int(config.memory * 1024)
        if config.gpu:
            new_sandbox = modal.Sandbox.create(
                image=modal_image,
                app=app,
                timeout=config.timeout,
                cpu=config.cpu,
                memory=memory_mb,
                unencrypted_ports=[CONTAINER_SSH_PORT],
                gpu=config.gpu,
                region=config.region,
            )
        else:
            new_sandbox = modal.Sandbox.create(
                image=modal_image,
                app=app,
                timeout=config.timeout,
                cpu=config.cpu,
                memory=memory_mb,
                unencrypted_ports=[CONTAINER_SSH_PORT],
                region=config.region,
            )
        logger.info("Created sandbox from snapshot: {}", new_sandbox.object_id)

        # Set up SSH and create host object using shared helper
        restored_host, ssh_host, ssh_port, host_public_key = self._setup_sandbox_ssh_and_create_host(
            sandbox=new_sandbox,
            host_id=host_id,
            host_name=host_name,
            user_tags=user_tags,
        )

        # Update host record on volume with new SSH info
        updated_host_record = host_record.model_copy(
            update={
                "ssh_host": ssh_host,
                "ssh_port": ssh_port,
                "ssh_host_public_key": host_public_key,
            }
        )
        self._write_host_record(updated_host_record)

        logger.info("Restored Modal host from snapshot: id={}, name={}", host_id, host_name)
        return restored_host

    @handle_modal_auth_error
    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        """Destroy a Modal sandbox permanently.

        If delete_snapshots is True, also deletes the host record from the volume.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        self.stop_host(host)

        if delete_snapshots:
            self._delete_host_record(host_id)

    # =========================================================================
    # Discovery Methods
    # =========================================================================

    @handle_modal_auth_error
    def get_host(
        self,
        host: HostId | HostName,
    ) -> Host:
        """Get a host by ID or name."""
        if isinstance(host, HostId):
            sandbox = self._find_sandbox_by_host_id(host)
            if sandbox is None:
                raise HostNotFoundError(host)
            host_obj = self._create_host_from_sandbox(sandbox)
            if host_obj is None:
                raise HostNotFoundError(host)
            return host_obj

        # If it's a HostName, search by name
        sandbox = self._find_sandbox_by_name(host)
        if sandbox is None:
            raise HostNotFoundError(host)
        host_obj = self._create_host_from_sandbox(sandbox)
        if host_obj is None:
            raise HostNotFoundError(host)
        return host_obj

    @handle_modal_auth_error
    def list_hosts(
        self,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List all active Modal sandbox hosts."""
        hosts: list[HostInterface] = []
        for sandbox in self._list_sandboxes():
            try:
                host_obj = self._create_host_from_sandbox(sandbox)
                if host_obj is not None:
                    hosts.append(host_obj)
            except (KeyError, ValueError) as e:
                # Skip sandboxes with invalid/missing tags
                logger.debug("Skipping sandbox with invalid tags: {}", e)
                continue
        return hosts

    def get_host_resources(self, host: HostInterface) -> HostResources:
        """Get resource information for a Modal sandbox."""
        # Read host record from volume
        host_record = self._read_host_record(host.id)
        if host_record is None:
            return HostResources(
                cpu=CpuResources(count=1, frequency_ghz=None),
                memory_gb=1.0,
                disk_gb=None,
                gpu=None,
            )

        cpu = host_record.config.cpu
        memory = host_record.config.memory

        return HostResources(
            # Modal allows fractional CPUs (e.g., 0.5), but count must be at least 1
            cpu=CpuResources(count=max(1, int(cpu)), frequency_ghz=None),
            memory_gb=memory,
            disk_gb=None,
            gpu=None,
        )

    # =========================================================================
    # Snapshot Methods
    # =========================================================================

    @handle_modal_auth_error
    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        """Create a snapshot of a Modal sandbox's filesystem.

        Uses Modal's sandbox.snapshot_filesystem() to create an incremental snapshot.
        Snapshot metadata is stored on the Modal Volume for persistence across
        sandbox termination and sharing between mngr instances.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.debug("Creating snapshot for Modal sandbox: host_id={}", host_id)

        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            raise HostNotFoundError(host_id)

        # Read existing host record from volume
        host_record = self._read_host_record(host_id)
        if host_record is None:
            raise HostNotFoundError(host_id)

        # Create the filesystem snapshot
        logger.debug("Calling snapshot_filesystem on sandbox")
        modal_image = sandbox.snapshot_filesystem()
        modal_image_id = modal_image.object_id

        # Generate mngr snapshot ID and metadata
        snapshot_id = SnapshotId.generate()
        created_at = datetime.now(timezone.utc)
        # Use last 8 characters of the snapshot ID as a short identifier for the default name
        short_id = str(snapshot_id)[-8:]
        snapshot_name = name if name is not None else SnapshotName(f"snapshot-{short_id}")

        new_snapshot = SnapshotRecord(
            id=str(snapshot_id),
            name=str(snapshot_name),
            created_at=created_at.isoformat(),
            modal_image_id=modal_image_id,
        )

        # Update host record with new snapshot and write to volume
        updated_host_record = host_record.model_copy(
            update={"snapshots": list(host_record.snapshots) + [new_snapshot]}
        )
        self._write_host_record(updated_host_record)

        logger.info(
            "Created snapshot: id={}, name={}, modal_image_id={}",
            snapshot_id,
            snapshot_name,
            modal_image_id,
        )
        return snapshot_id

    def list_snapshots(
        self,
        host: HostInterface | HostId,
    ) -> list[SnapshotInfo]:
        """List all snapshots for a Modal sandbox.

        Reads snapshot metadata from the Modal Volume, which persists even
        after the sandbox has been terminated.
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Read host record from volume
        host_record = self._read_host_record(host_id)
        if host_record is None:
            return []

        # Convert to SnapshotInfo objects, sorted by created_at (newest first)
        snapshots: list[SnapshotInfo] = []
        sorted_snapshots = sorted(host_record.snapshots, key=lambda s: s.created_at, reverse=True)
        for idx, snap_record in enumerate(sorted_snapshots):
            created_at_str = snap_record.created_at
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(timezone.utc)
            snapshots.append(
                SnapshotInfo(
                    id=SnapshotId(snap_record.id),
                    name=SnapshotName(snap_record.name),
                    created_at=created_at,
                    size_bytes=None,
                    recency_idx=idx,
                )
            )

        return snapshots

    def delete_snapshot(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId,
    ) -> None:
        """Delete a snapshot from a Modal sandbox.

        Removes the snapshot metadata from the Modal Volume. Note that the
        underlying Modal image is not deleted since Modal doesn't yet provide
        a way to delete images via their API; they will be garbage-collected
        by Modal when no longer referenced.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.debug("Deleting snapshot {} from Modal sandbox: host_id={}", snapshot_id, host_id)

        # Read host record from volume
        host_record = self._read_host_record(host_id)
        if host_record is None:
            raise HostNotFoundError(host_id)

        # Find and remove the snapshot
        snapshot_id_str = str(snapshot_id)
        updated_snapshots = [s for s in host_record.snapshots if s.id != snapshot_id_str]

        if len(updated_snapshots) == len(host_record.snapshots):
            raise SnapshotNotFoundError(snapshot_id)

        # Update host record on volume
        updated_host_record = host_record.model_copy(update={"snapshots": updated_snapshots})
        self._write_host_record(updated_host_record)

        logger.info("Deleted snapshot: {}", snapshot_id)

    # =========================================================================
    # Volume Methods (not supported)
    # =========================================================================

    def list_volumes(self) -> list[VolumeInfo]:
        return []

    def delete_volume(self, volume_id: VolumeId) -> None:
        raise NotImplementedError("Modal provider does not support volumes")

    # =========================================================================
    # Host Mutation Methods
    # =========================================================================

    def get_host_tags(
        self,
        host: HostInterface | HostId,
    ) -> dict[str, str]:
        """Get user-defined tags for a host (excludes internal mngr tags).

        Reads from the volume, which persists even after sandbox termination.
        Falls back to sandbox tags if volume record doesn't exist yet.
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Try to read from volume first (source of truth)
        host_record = self._read_host_record(host_id)
        if host_record is not None:
            return dict(host_record.user_tags)

        # Fall back to sandbox tags
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            return {}

        tags = sandbox.get_tags()
        user_tags: dict[str, str] = {}
        for key, value in tags.items():
            if key.startswith(TAG_USER_PREFIX):
                user_key = key[len(TAG_USER_PREFIX) :]
                user_tags[user_key] = value
        return user_tags

    def set_host_tags(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Replace all user-defined tags on a host.

        Updates both sandbox tags (for quick access) and volume (for persistence).
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Update sandbox tags if sandbox is running
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            current_tags = sandbox.get_tags()
            new_tags: dict[str, str] = {}
            for key, value in current_tags.items():
                if not key.startswith(TAG_USER_PREFIX):
                    new_tags[key] = value
            for key, value in tags.items():
                new_tags[TAG_USER_PREFIX + key] = value
            sandbox.set_tags(new_tags)

        # Update volume record
        host_record = self._read_host_record(host_id)
        if host_record is not None:
            updated_host_record = host_record.model_copy(update={"user_tags": dict(tags)})
            self._write_host_record(updated_host_record)

    def add_tags_to_host(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Add or update tags on a host.

        Updates both sandbox tags (for quick access) and volume (for persistence).
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Update sandbox tags if sandbox is running
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            current_tags = sandbox.get_tags()
            new_tags = dict(current_tags)
            for key, value in tags.items():
                new_tags[TAG_USER_PREFIX + key] = value
            sandbox.set_tags(new_tags)

        # Update volume record
        host_record = self._read_host_record(host_id)
        if host_record is not None:
            merged_tags = dict(host_record.user_tags)
            merged_tags.update(tags)
            updated_host_record = host_record.model_copy(update={"user_tags": merged_tags})
            self._write_host_record(updated_host_record)

    def remove_tags_from_host(
        self,
        host: HostInterface | HostId,
        keys: Sequence[str],
    ) -> None:
        """Remove tags from a host by key.

        Updates both sandbox tags (for quick access) and volume (for persistence).
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Update sandbox tags if sandbox is running
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            current_tags = sandbox.get_tags()
            new_tags: dict[str, str] = {}
            keys_to_remove = {TAG_USER_PREFIX + k for k in keys}
            for key, value in current_tags.items():
                if key not in keys_to_remove:
                    new_tags[key] = value
            sandbox.set_tags(new_tags)

        # Update volume record
        host_record = self._read_host_record(host_id)
        if host_record is not None:
            updated_tags = {k: v for k, v in host_record.user_tags.items() if k not in keys}
            updated_host_record = host_record.model_copy(update={"user_tags": updated_tags})
            self._write_host_record(updated_host_record)

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> Host:
        """Rename a host.

        Updates both sandbox tags (for quick access) and volume (for persistence).
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Update sandbox tags if sandbox is running
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            current_tags = sandbox.get_tags()
            current_tags[TAG_HOST_NAME] = str(name)
            sandbox.set_tags(current_tags)

        # Update volume record
        host_record = self._read_host_record(host_id)
        if host_record is not None:
            updated_host_record = host_record.model_copy(update={"host_name": str(name)})
            self._write_host_record(updated_host_record)

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

        # Read host record from volume
        host_record = self._read_host_record(host_id)
        if host_record is None:
            raise HostNotFoundError(host_id)

        # Add the host key to known_hosts so SSH connections will work
        add_host_to_known_hosts(
            self._known_hosts_path,
            host_record.ssh_host,
            host_record.ssh_port,
            host_record.ssh_host_public_key,
        )

        private_key_path, _ = self._get_ssh_keypair()
        return self._create_pyinfra_host(
            host_record.ssh_host,
            host_record.ssh_port,
            private_key_path,
        )

    # =========================================================================
    # Lifecycle Methods
    # =========================================================================

    def close(self) -> None:
        """Clean up the Modal app context.

        Exits the app.run() context manager if one was created for this app_name.
        This makes the app ephemeral and prevents accumulation.
        """
        self.modal_app.close()


def _build_modal_secrets_from_env(
    env_var_names: Sequence[str],
) -> list[modal.Secret]:
    """Build Modal secrets from environment variable names.

    Reads the values of the specified environment variables from the current
    environment and creates a Modal secret containing them. This allows
    Dockerfiles to access secrets during build via --mount=type=secret.

    Raises MngrError if any specified environment variable is not set.
    """
    if not env_var_names:
        return []

    secret_dict: dict[str, str | None] = {}
    missing_vars: list[str] = []

    for var_name in env_var_names:
        value = os.environ.get(var_name)
        if value is None:
            missing_vars.append(var_name)
        else:
            secret_dict[var_name] = value

    if missing_vars:
        raise MngrError(
            f"Environment variable(s) not set for secrets: {', '.join(missing_vars)}. "
            "Set these environment variables before building."
        )

    logger.debug("Creating Modal secrets from {} environment variable(s)", len(secret_dict))
    return [modal.Secret.from_dict(secret_dict)]


def _build_image_from_dockerfile_contents(
    dockerfile_contents: str,
    # build context directory for COPY/ADD instructions
    context_dir: Path | None = None,
    # starting image; if not provided, uses FROM instruction in the dockerfile
    initial_image: modal.Image | None = None,
    # if True, apply each instruction separately for per-layer caching; if False, apply
    # all instructions at once (faster but no intermediate caching on failure)
    is_each_layer_cached: bool = True,
    # Modal secrets to make available during Dockerfile RUN commands
    secrets: Sequence[modal.Secret] = (),
) -> modal.Image:
    """Build a Modal image from Dockerfile contents with optional per-layer caching.

    When is_each_layer_cached=True (the default), each instruction is applied separately,
    allowing Modal to cache intermediate layers. This means if a build fails at step N,
    steps 1 through N-1 don't need to be re-run. Multistage dockerfiles are not supported.

    Secrets are passed to dockerfile_commands and are available during RUN commands
    via --mount=type=secret,id=<env_var_name>.
    """
    # DockerfileParser writes to a file, so use a temp directory to avoid conflicts
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpfile = Path(tmpdir) / "Dockerfile"
        dfp = DockerfileParser(str(tmpfile))
        dfp.content = dockerfile_contents

        assert not dfp.is_multistage, "Multistage Dockerfiles are not supported yet"

        last_from_index = None
        for i, instr in enumerate(dfp.structure):
            if instr["instruction"] == "FROM":
                last_from_index = i

        if initial_image is None:
            assert last_from_index is not None, "Dockerfile must have a FROM instruction"
            instructions = dfp.structure[last_from_index + 1 :]
            modal_image = modal.Image.from_registry(dfp.baseimage)
        else:
            assert last_from_index is None, "If initial_image is provided, Dockerfile cannot have a FROM instruction"
            instructions = list(dfp.structure)
            modal_image = initial_image

        if len(instructions) > 0:
            secrets_list = list(secrets)
            expanded_context_dir = context_dir.expanduser() if context_dir is not None else None
            if is_each_layer_cached:
                for instr in instructions:
                    if instr["instruction"] == "COMMENT":
                        continue
                    modal_image = modal_image.dockerfile_commands(
                        [instr["content"]],
                        context_dir=expanded_context_dir,
                        secrets=secrets_list,
                    )
            else:
                # The downside of doing them all at once is that if any one fails,
                # Modal will re-run all of them
                modal_image = modal_image.dockerfile_commands(
                    [x["content"] for x in instructions if x["instruction"] != "COMMENT"],
                    context_dir=expanded_context_dir,
                    secrets=secrets_list,
                )

        return modal_image
