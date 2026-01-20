"""Modal provider instance implementation.

Manages Modal sandboxes as hosts with SSH access via pyinfra.
"""

import argparse
import json
import socket
import time
from pathlib import Path
from typing import Any
from typing import Final
from typing import Mapping
from typing import Sequence

import modal
from loguru import logger
from pydantic import Field
from pyinfra.api import Host as PyinfraHost
from pyinfra.api import State as PyinfraState
from pyinfra.api.inventory import Inventory

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import SnapshotsNotSupportedError
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
from imbue.mngr.providers.modal.ssh_utils import add_host_to_known_hosts
from imbue.mngr.providers.modal.ssh_utils import load_or_create_host_keypair
from imbue.mngr.providers.modal.ssh_utils import load_or_create_ssh_keypair

# Module-level registry of app contexts by app name
# This ensures we only create one app per unique app_name, even if multiple
# ModalProviderInstance objects are created with the same app_name
_app_registry: dict[str, tuple[modal.App, "_ModalAppContextHandle"]] = {}


class _ModalAppContextHandle(FrozenModel):
    """Handle for managing a Modal app context lifecycle.

    This class captures a Modal app's run context and provides a method to exit it.
    It's used to avoid inline function definitions which violate the style guide.
    """

    run_context: Any = Field(description="The Modal app.run() context manager")
    app_name: str = Field(description="The name of the Modal app")


def _exit_modal_app_context(handle: _ModalAppContextHandle) -> None:
    """Exit a Modal app context.

    This is a module-level function instead of a method to avoid inline functions.
    """
    logger.debug("Exiting Modal app context: {}", handle.app_name)
    try:
        handle.run_context.__exit__(None, None, None)
    except modal.exception.Error as e:
        logger.warning("Modal error exiting app context {}: {}", handle.app_name, e)


def reset_modal_app_registry() -> None:
    """Reset the modal app registry.

    Closes all open app contexts and clears the registry. This is primarily used
    for test isolation to ensure a clean state between tests.
    """
    for app_name, (_, context_handle) in list(_app_registry.items()):
        try:
            _exit_modal_app_context(context_handle)
        except modal.exception.Error as e:
            logger.debug("Modal error closing app {} during reset: {}", app_name, e)
    _app_registry.clear()


# Constants
CONTAINER_SSH_PORT = 22
# 2 minutes default sandbox lifetime (so that we don't just leave tons of them running--we're not doing a good job of cleaning them up yet)
DEFAULT_SANDBOX_TIMEOUT = 2 * 60
# Seconds to wait for sshd to be ready
SSH_CONNECT_TIMEOUT = 60

# Tag key constants for sandbox metadata stored in Modal tags
# Modal has a limit of 10 tags per sandbox, so we use only 3 for mngr metadata
# (leaving 7 for user tags with the TAG_USER_PREFIX)
TAG_HOST_ID: Final[str] = "mngr_host_id"
TAG_HOST_NAME: Final[str] = "mngr_host_name"
# TAG_HOST_RECORD contains a JSON blob with SSH info and sandbox config
TAG_HOST_RECORD: Final[str] = "mngr_host_record"
TAG_USER_PREFIX: Final[str] = "mngr_user_"


class SandboxConfig(FrozenModel):
    """Configuration parsed from build arguments."""

    gpu: str | None = None
    cpu: float = 1.0
    memory: float = 1.0
    image: str | None = None
    timeout: int = DEFAULT_SANDBOX_TIMEOUT


class ModalProviderInstance(BaseProviderInstance):
    """Provider instance for managing Modal sandboxes as hosts.

    Each sandbox runs sshd and is accessed via pyinfra's SSH connector.
    Sandboxes have a maximum lifetime (timeout) after which they are automatically
    terminated by Modal.

    Sandbox metadata (host_id, name, SSH info, config) is stored in Modal tags,
    allowing the provider to rediscover sandboxes across program restarts using
    Modal's Sandbox.list() API.
    """

    app_name: str = Field(frozen=True, description="Modal app name for sandboxes")
    default_timeout: int = Field(frozen=True, description="Default sandbox timeout in seconds")
    default_cpu: float = Field(frozen=True, description="Default CPU cores")
    default_memory: float = Field(frozen=True, description="Default memory in GB")

    # FIXME: actually, modal *does* support snapshots! calling sandbox.snapshot_filesystem() returns an image, which you can pull the ID off of.
    #  In order to actually implement this correctly, we'll need to save the snapshot IDs into a label for now (since there are not yet any routes for listing snapshots from Modal)
    #  They'll eventually add them, so for now it's fine to just make a label called "snapshots" that contains a comma-separated list of snapshot IDs.
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
        # Store keys under the mngr config directory (test-scoped when running tests)
        config_dir = self.mngr_ctx.config.default_host_dir.expanduser()
        return config_dir / "providers" / "modal" / str(self.name)

    # FIXME: we should simplify this--just have a *single* keypair for a given provider backend (it can be configured, but should be shared across all instances of the same backend)
    #  Yes, this is less secure, but it's way simpler to manage, and Modal sandboxes are ephemeral anyway, and we can easily come back to this later.
    #  Then we'll have a few less keys to keep track of.
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

    def _build_modal_image(self, base_image: str | None = None) -> modal.Image:
        """Build a Modal image with SSH support.

        If base_image is provided (e.g., "python:3.11-slim"), uses that as the
        base. Otherwise uses debian:bookworm-slim.
        """
        if base_image:
            image = modal.Image.from_registry(base_image)
        else:
            image = modal.Image.debian_slim()

        # FIXME: all of these commands should be done at the _start_sshd_in_sandbox time instead of build time
        #  The reason is that we want to warn if tmux or sshd was not already configured in the base image (and only install after warning)

        # Install SSH server and tmux
        image = image.apt_install("openssh-server", "tmux")

        # Create sshd run directory
        image = image.run_commands(["mkdir -p /run/sshd"])

        # Create mngr host directory
        image = image.run_commands([f"mkdir -p {self.host_dir}"])

        return image

    def _start_sshd_in_sandbox(
        self,
        sandbox: modal.Sandbox,
        client_public_key: str,
        host_private_key: str,
        host_public_key: str,
    ) -> None:
        """Set up SSH access and start sshd in the sandbox."""
        # Create .ssh directory
        sandbox.exec("mkdir", "-p", "/root/.ssh")

        # Write the authorized_keys file (for client authentication)
        with sandbox.open("/root/.ssh/authorized_keys", "wb") as f:
            f.write(client_public_key.encode("utf-8"))

        # Install the host key (for host identification)
        # This ensures all Modal sandboxes use the same host key that we control
        with sandbox.open("/etc/ssh/ssh_host_ed25519_key", "wb") as f:
            f.write(host_private_key.encode("utf-8"))

        with sandbox.open("/etc/ssh/ssh_host_ed25519_key.pub", "wb") as f:
            f.write(host_public_key.encode("utf-8"))

        # Set correct permissions on host key
        sandbox.exec("chmod", "600", "/etc/ssh/ssh_host_ed25519_key")
        sandbox.exec("chmod", "644", "/etc/ssh/ssh_host_ed25519_key.pub")

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
        host_data = {
            "ssh_user": "root",
            "ssh_port": port,
            "ssh_key": str(private_key_path),
            "ssh_known_hosts_file": str(self._known_hosts_path),
            "ssh_strict_host_key_checking": "yes",
        }

        names_data = ([(hostname, host_data)], {})
        inventory = Inventory(names_data)
        state = PyinfraState(inventory=inventory)

        pyinfra_host = inventory.get_host(hostname)
        pyinfra_host.init(state)

        return pyinfra_host

    def _parse_build_args(self, build_args: Sequence[str] | None) -> SandboxConfig:
        """Parse build arguments into sandbox configuration.

        Accepts arguments in two formats:
        - Key-value: gpu=h100, cpu=2, memory=4
        - Flag style: --gpu=h100, --gpu h100

        Both formats can be mixed. Unknown arguments raise an error.
        """
        if not build_args:
            return SandboxConfig(
                gpu=None,
                cpu=self.default_cpu,
                memory=self.default_memory,
                image=None,
                timeout=self.default_timeout,
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
        parser.add_argument("--cpu", type=float, default=self.default_cpu)
        parser.add_argument("--memory", type=float, default=self.default_memory)
        parser.add_argument("--image", type=str, default=None)
        parser.add_argument("--timeout", type=int, default=self.default_timeout)

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
            timeout=parsed.timeout,
        )

    # =========================================================================
    # Tag Management Helpers
    # =========================================================================

    def _build_sandbox_tags(
        self,
        host_id: HostId,
        name: HostName,
        ssh_host: str,
        ssh_port: int,
        host_public_key: str,
        config: SandboxConfig,
        user_tags: Mapping[str, str] | None,
    ) -> dict[str, str]:
        """Build the tags dict to store on a Modal sandbox.

        Uses only 3 mngr tags (host_id, host_name, host_record) to stay well
        under Modal's 10-tag limit, leaving 7 tags for user-defined tags.
        """
        # Build the host record as a JSON blob containing all other metadata
        host_record: dict[str, Any] = {
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "ssh_host_public_key": host_public_key,
            "config": {
                "cpu": config.cpu,
                "memory": config.memory,
                "timeout": config.timeout,
                "gpu": config.gpu,
                "image": config.image,
            },
        }

        tags: dict[str, str] = {
            TAG_HOST_ID: str(host_id),
            TAG_HOST_NAME: str(name),
            TAG_HOST_RECORD: json.dumps(host_record),
        }

        # Store user tags with a prefix to separate them from mngr tags
        if user_tags:
            for key, value in user_tags.items():
                tags[TAG_USER_PREFIX + key] = value

        return tags

    def _parse_sandbox_tags(
        self,
        tags: dict[str, str],
    ) -> tuple[HostId, HostName, str, int, str | None, SandboxConfig, dict[str, str]]:
        """Parse tags from a Modal sandbox into structured data.

        The returned tuple contains (host_id, name, ssh_host, ssh_port, host_public_key, config, user_tags).
        host_public_key may be None for sandboxes created before we started storing it in tags.
        """
        host_id = HostId(tags[TAG_HOST_ID])
        name = HostName(tags[TAG_HOST_NAME])

        # Parse the host record JSON blob (required for new sandboxes)
        # Accessing tags[TAG_HOST_RECORD] will raise KeyError if missing,
        # which is caught by callers like list_hosts to skip old sandboxes
        host_record = json.loads(tags[TAG_HOST_RECORD])
        ssh_host = host_record["ssh_host"]
        ssh_port = host_record["ssh_port"]
        host_public_key = host_record.get("ssh_host_public_key")
        config_data = host_record.get("config", {})
        config = SandboxConfig(
            cpu=float(config_data.get("cpu", self.default_cpu)),
            memory=float(config_data.get("memory", self.default_memory)),
            gpu=config_data.get("gpu"),
            image=config_data.get("image"),
            timeout=int(config_data.get("timeout", self.default_timeout)),
        )

        # Extract user tags (those with the user prefix)
        user_tags: dict[str, str] = {}
        for key, value in tags.items():
            if key.startswith(TAG_USER_PREFIX):
                user_key = key[len(TAG_USER_PREFIX) :]
                user_tags[user_key] = value

        return host_id, name, ssh_host, ssh_port, host_public_key, config, user_tags

    def _get_modal_app(self) -> modal.App:
        """Get or create the Modal app for this provider instance.

        Creates an ephemeral app with `modal.App(name)` and enters its `app.run()`
        context manager. The app is cached in a module-level registry by name, so
        multiple ModalProviderInstance objects with the same app_name will share
        the same app instance.

        The context is exited when `close()` is called, making the app ephemeral
        and preventing accumulation of apps (which can hit Modal's limits).

        Raises modal.exception.AuthError if Modal credentials are not configured.
        """
        if self.app_name in _app_registry:
            app, _ = _app_registry[self.app_name]
            return app

        logger.debug("Creating ephemeral Modal app: {}", self.app_name)
        app = modal.App(self.app_name)

        # Enter the app.run() context manager manually so we can return the app
        # while keeping the context active until close() is called
        run_context = app.run()
        run_context.__enter__()

        context_handle = _ModalAppContextHandle(run_context=run_context, app_name=self.app_name)
        _app_registry[self.app_name] = (app, context_handle)
        return app

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

    def _list_mngr_sandboxes(self) -> list[modal.Sandbox]:
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

        This adds the host key to known_hosts for the sandbox's SSH endpoint,
        enabling SSH connections to succeed without host key verification prompts.

        Returns None if the sandbox doesn't have the required metadata stored in tags
        (which happens for sandboxes created before we started storing the host public key).
        """
        tags = sandbox.get_tags()
        host_id, name, ssh_host, ssh_port, host_public_key, config, user_tags = self._parse_sandbox_tags(tags)

        if host_public_key is None:
            # Sandbox was created before we started storing the host public key.
            # We can't connect to it because we don't know its host key.
            logger.debug("Skipping sandbox {} - no host public key in tags", sandbox.object_id)
            return None

        # Add the sandbox's host key to known_hosts so SSH connections will work
        add_host_to_known_hosts(self._known_hosts_path, ssh_host, ssh_port, host_public_key)

        private_key_path, _ = self._get_ssh_keypair()
        pyinfra_host = self._create_pyinfra_host(ssh_host, ssh_port, private_key_path)
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

    def create_host(
        self,
        name: HostName,
        image: ImageReference | None = None,
        tags: Mapping[str, str] | None = None,
        build_args: Sequence[str] | None = None,
        start_args: Sequence[str] | None = None,
    ) -> Host:
        """Create a new Modal sandbox host."""
        logger.info("Creating Modal sandbox host: name={}", name)

        # Parse build arguments
        config = self._parse_build_args(build_args)
        base_image = str(image) if image else config.image

        # Get SSH client keypair (for authentication)
        private_key_path, client_public_key = self._get_ssh_keypair()
        logger.debug("Using SSH client key: {}", private_key_path)

        # Get SSH host keypair (for host identification)
        host_key_path, host_public_key = self._get_host_keypair()
        host_private_key = host_key_path.read_text()
        logger.debug("Using SSH host key: {}", host_key_path)

        # Build the Modal image
        logger.debug("Building Modal image...")
        modal_image = self._build_modal_image(base_image)

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
        if config.gpu:
            sandbox = modal.Sandbox.create(
                image=modal_image,
                app=app,
                timeout=config.timeout,
                cpu=config.cpu,
                memory=memory_mb,
                unencrypted_ports=[CONTAINER_SSH_PORT],
                gpu=config.gpu,
            )
        else:
            sandbox = modal.Sandbox.create(
                image=modal_image,
                app=app,
                timeout=config.timeout,
                cpu=config.cpu,
                memory=memory_mb,
                unencrypted_ports=[CONTAINER_SSH_PORT],
            )
        logger.info("Created sandbox: {}", sandbox.object_id)

        # Start sshd with our host key
        logger.debug("Starting sshd in sandbox...")
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

        # Generate host ID
        host_id = HostId.generate()

        # Store metadata as tags on the sandbox (enables discovery across restarts)
        sandbox_tags = self._build_sandbox_tags(
            host_id=host_id,
            name=name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            host_public_key=host_public_key,
            config=config,
            user_tags=tags,
        )
        logger.debug("Setting sandbox tags: {}", list(sandbox_tags.keys()))
        sandbox.set_tags(sandbox_tags)

        # Create pyinfra host
        pyinfra_host = self._create_pyinfra_host(ssh_host, ssh_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        # Create and return the Host object
        host = Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

        logger.info("Modal host created: id={}, name={}, ssh={}:{}", host_id, name, ssh_host, ssh_port)
        return host

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

    def start_host(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId | None = None,
    ) -> Host:
        """Start a stopped host.

        Note: Modal sandboxes cannot be restarted once terminated. This will
        raise an error if the sandbox is not currently running.
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            raise MngrError(
                f"Modal sandbox {host_id} is not running and cannot be restarted. Create a new host instead."
            )

        host_obj = self._create_host_from_sandbox(sandbox)
        if host_obj is None:
            raise MngrError(
                f"Modal sandbox {host_id} is missing required metadata and cannot be reconnected. Create a new host instead."
            )
        return host_obj

    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        """Destroy a Modal sandbox permanently."""
        self.stop_host(host)

    # =========================================================================
    # Discovery Methods
    # =========================================================================

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

    def list_hosts(
        self,
        include_destroyed: bool = False,
    ) -> list[HostInterface]:
        """List all active Modal sandbox hosts."""
        hosts: list[HostInterface] = []
        for sandbox in self._list_mngr_sandboxes():
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
        sandbox = self._find_sandbox_by_host_id(host.id)
        if sandbox is None:
            return HostResources(
                cpu=CpuResources(count=1, frequency_ghz=None),
                memory_gb=1.0,
                disk_gb=None,
                gpu=None,
            )

        tags = sandbox.get_tags()
        host_record_json = tags.get(TAG_HOST_RECORD)
        if not host_record_json:
            return HostResources(
                cpu=CpuResources(count=1, frequency_ghz=None),
                memory_gb=1.0,
                disk_gb=None,
                gpu=None,
            )

        host_record = json.loads(host_record_json)
        config_data = host_record.get("config", {})
        cpu = float(config_data.get("cpu", self.default_cpu))
        memory = float(config_data.get("memory", self.default_memory))

        return HostResources(
            # Modal allows fractional CPUs (e.g., 0.5), but count must be at least 1
            cpu=CpuResources(count=max(1, int(cpu)), frequency_ghz=None),
            memory_gb=memory,
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
        raise SnapshotsNotSupportedError(self.name)

    def list_snapshots(
        self,
        host: HostInterface | HostId,
    ) -> list[SnapshotInfo]:
        return []

    def delete_snapshot(
        self,
        host: HostInterface | HostId,
        snapshot_id: SnapshotId,
    ) -> None:
        raise SnapshotsNotSupportedError(self.name)

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
        """Get user-defined tags for a host (excludes internal mngr tags)."""
        host_id = host.id if isinstance(host, HostInterface) else host
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            return {}

        tags = sandbox.get_tags()
        # Extract only user tags (those with the user prefix)
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
        """Replace all user-defined tags on a host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            return

        # Get current tags and preserve mngr tags
        current_tags = sandbox.get_tags()
        new_tags: dict[str, str] = {}
        for key, value in current_tags.items():
            if not key.startswith(TAG_USER_PREFIX):
                new_tags[key] = value

        # Add new user tags
        for key, value in tags.items():
            new_tags[TAG_USER_PREFIX + key] = value

        sandbox.set_tags(new_tags)

    def add_tags_to_host(
        self,
        host: HostInterface | HostId,
        tags: Mapping[str, str],
    ) -> None:
        """Add or update tags on a host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            return

        current_tags = sandbox.get_tags()
        new_tags = dict(current_tags)
        for key, value in tags.items():
            new_tags[TAG_USER_PREFIX + key] = value
        sandbox.set_tags(new_tags)

    def remove_tags_from_host(
        self,
        host: HostInterface | HostId,
        keys: Sequence[str],
    ) -> None:
        """Remove tags from a host by key."""
        host_id = host.id if isinstance(host, HostInterface) else host
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            return

        current_tags = sandbox.get_tags()
        new_tags: dict[str, str] = {}
        keys_to_remove = {TAG_USER_PREFIX + k for k in keys}
        for key, value in current_tags.items():
            if key not in keys_to_remove:
                new_tags[key] = value
        sandbox.set_tags(new_tags)

    def rename_host(
        self,
        host: HostInterface | HostId,
        name: HostName,
    ) -> Host:
        """Rename a host."""
        host_id = host.id if isinstance(host, HostInterface) else host
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            current_tags = sandbox.get_tags()
            current_tags[TAG_HOST_NAME] = str(name)
            sandbox.set_tags(current_tags)
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
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
            raise HostNotFoundError(host_id)

        tags = sandbox.get_tags()
        host_record_json = tags.get(TAG_HOST_RECORD)
        if not host_record_json:
            raise HostNotFoundError(host_id)

        host_record = json.loads(host_record_json)
        ssh_host = host_record.get("ssh_host")
        ssh_port = host_record.get("ssh_port")
        host_public_key = host_record.get("ssh_host_public_key")

        if ssh_host is None or ssh_port is None:
            raise HostNotFoundError(host_id)

        # Add the host key to known_hosts so SSH connections will work
        if host_public_key is not None:
            add_host_to_known_hosts(self._known_hosts_path, ssh_host, ssh_port, host_public_key)

        private_key_path, _ = self._get_ssh_keypair()
        return self._create_pyinfra_host(
            ssh_host,
            ssh_port,
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
        if self.app_name in _app_registry:
            _, context_handle = _app_registry.pop(self.app_name)
            _exit_modal_app_context(context_handle)
