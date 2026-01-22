"""Modal provider instance implementation.

Manages Modal sandboxes as hosts with SSH access via pyinfra.
"""

import argparse
import contextlib
import io
import json
import socket
import sys
import tempfile
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Final
from typing import Mapping
from typing import Sequence
from typing import cast

import modal
from dockerfile_parse import DockerfileParser
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
from imbue.mngr.providers.modal.log_utils import enable_modal_output_capture
from imbue.mngr.providers.modal.ssh_utils import add_host_to_known_hosts
from imbue.mngr.providers.modal.ssh_utils import load_or_create_host_keypair
from imbue.mngr.providers.modal.ssh_utils import load_or_create_ssh_keypair

# Module-level registry of app contexts by app name
# This ensures we only create one app per unique app_name, even if multiple
# ModalProviderInstance objects are created with the same app_name
_app_registry: dict[str, tuple[modal.App, "_ModalAppContextHandle"]] = {}


class _ModalAppContextHandle(FrozenModel):
    """Handle for managing a Modal app context lifecycle with output capture.

    This class captures a Modal app's run context along with the output capture
    context. The output buffer can be inspected to detect build failures and
    other issues in the Modal logs.
    """

    run_context: Any = Field(description="The Modal app.run() context manager")
    app_name: str = Field(description="The name of the Modal app")
    output_capture_context: Any = Field(description="The output capture context manager")
    output_buffer: Any = Field(description="StringIO buffer containing captured Modal output")
    loguru_writer: Any = Field(description="Loguru writer for structured logging (or None)")


def _exit_modal_app_context(handle: _ModalAppContextHandle) -> None:
    """Exit a Modal app context and its output capture context.

    This is a module-level function instead of a method to avoid inline functions.
    """
    logger.debug("Exiting Modal app context: {}", handle.app_name)

    # Log any captured output for debugging
    captured_output = handle.output_buffer.getvalue()
    if captured_output:
        logger.trace("Modal output captured ({} chars): {}", len(captured_output), captured_output[:500])

    # Exit the app context first, redirecting stdout to suppress "Stopping app" message.
    # Modal prints directly to stdout during context exit, bypassing OutputManager.
    exit_capture = io.StringIO()
    original_stdout = sys.stdout
    try:
        sys.stdout = exit_capture
        handle.run_context.__exit__(None, None, None)
    except modal.exception.Error as e:
        logger.warning("Modal error exiting app context {}: {}", handle.app_name, e)
    finally:
        sys.stdout = original_stdout

    # Log any exit messages that were captured
    exit_output = exit_capture.getvalue()
    if exit_output.strip():
        logger.debug("Modal exit: {}", exit_output.strip())

    # Exit the output capture context - this is a cleanup operation so we just
    # suppress any errors
    with contextlib.suppress(OSError, RuntimeError):
        handle.output_capture_context.__exit__(None, None, None)


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


def build_image_from_dockerfile_contents(
    dockerfile_contents: str,
    # build context directory for COPY/ADD instructions
    context_dir: Path | None = None,
    # starting image; if not provided, uses FROM instruction in the dockerfile
    initial_image: modal.Image | None = None,
    # if True, apply each instruction separately for per-layer caching; if False, apply
    # all instructions at once (faster but no intermediate caching on failure)
    is_each_layer_cached: bool = True,
) -> modal.Image:
    """Build a Modal image from Dockerfile contents with optional per-layer caching.

    When is_each_layer_cached=True (the default), each instruction is applied separately,
    allowing Modal to cache intermediate layers. This means if a build fails at step N,
    steps 1 through N-1 don't need to be re-run. Multistage dockerfiles are not supported.
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
            if is_each_layer_cached:
                for instr in instructions:
                    if instr["instruction"] == "COMMENT":
                        continue
                    modal_image = modal_image.dockerfile_commands(
                        [instr["content"]],
                        context_dir=context_dir,
                    )
            else:
                # The downside of doing them all at once is that if any one fails,
                # Modal will re-run all of them
                modal_image = modal_image.dockerfile_commands(
                    [x["content"] for x in instructions if x["instruction"] != "COMMENT"],
                    context_dir=context_dir,
                )

        return modal_image


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
    dockerfile: str | None = None
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
    def _keys_dir(self) -> Path:
        """Get the directory for storing SSH keys.

        Uses a single directory shared across all modal provider instances for
        simplicity. Modal sandboxes are ephemeral, so the security tradeoff of
        sharing keys is acceptable.
        """
        # Store keys under the mngr config directory (test-scoped when running tests)
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

    @property
    def _snapshots_dir(self) -> Path:
        """Get the directory for storing snapshot metadata persistently.

        Snapshots need to be stored locally because Modal sandbox tags are lost
        when the sandbox is terminated. This allows restoration from snapshots
        even after the original sandbox is gone.
        """
        return self._keys_dir / "snapshots"

    def _get_snapshot_file_path(self, host_id: HostId, snapshot_id: SnapshotId) -> Path:
        """Get the file path for a specific snapshot's metadata."""
        return self._snapshots_dir / str(host_id) / f"{snapshot_id}.json"

    def _save_snapshot_locally(
        self,
        host_id: HostId,
        snapshot_data: dict[str, Any],
        host_metadata: dict[str, Any],
    ) -> None:
        """Save snapshot metadata to local storage for persistence across sandbox termination."""
        snapshot_id = SnapshotId(snapshot_data["id"])
        file_path = self._get_snapshot_file_path(host_id, snapshot_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Combine snapshot data with host metadata for restoration
        full_data = {
            "snapshot": snapshot_data,
            "host": host_metadata,
        }
        file_path.write_text(json.dumps(full_data, indent=2))

    def _load_snapshot_locally(
        self,
        host_id: HostId,
        snapshot_id: SnapshotId,
    ) -> dict[str, Any] | None:
        """Load snapshot metadata from local storage."""
        file_path = self._get_snapshot_file_path(host_id, snapshot_id)
        if not file_path.exists():
            return None
        return json.loads(file_path.read_text())

    def _delete_snapshot_locally(self, host_id: HostId, snapshot_id: SnapshotId) -> None:
        """Delete snapshot metadata from local storage."""
        file_path = self._get_snapshot_file_path(host_id, snapshot_id)
        if file_path.exists():
            file_path.unlink()

    def _list_snapshots_locally(self, host_id: HostId) -> list[dict[str, Any]]:
        """List all snapshots for a host from local storage.

        Returns snapshots sorted by created_at (oldest first) to match the order
        used when snapshots are stored in sandbox tags.
        """
        host_snapshots_dir = self._snapshots_dir / str(host_id)
        if not host_snapshots_dir.exists():
            return []

        snapshots: list[dict[str, Any]] = []
        for file_path in host_snapshots_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text())
                snapshots.append(data["snapshot"])
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by created_at timestamp (oldest first) to match sandbox tag ordering
        snapshots.sort(key=lambda s: s.get("created_at", ""))
        return snapshots

    def _delete_all_snapshots_locally(self, host_id: HostId) -> None:
        """Delete all local snapshot files for a host."""
        host_snapshots_dir = self._snapshots_dir / str(host_id)
        if not host_snapshots_dir.exists():
            return

        # Delete all snapshot files
        for file_path in host_snapshots_dir.glob("*.json"):
            try:
                file_path.unlink()
            except OSError:
                logger.debug("Failed to delete snapshot file: {}", file_path)

        # Remove the host directory if empty
        try:
            host_snapshots_dir.rmdir()
        except OSError:
            # Directory not empty or other error - ignore
            pass

    def _build_modal_image(
        self,
        base_image: str | None = None,
        dockerfile: Path | None = None,
    ) -> modal.Image:
        """Build a Modal image.

        If dockerfile is provided, builds from that Dockerfile with per-layer caching.
        Each instruction is applied separately, so if a build fails at step N,
        steps 1 through N-1 are cached and don't need to be re-run.

        Elif base_image is provided (e.g., "python:3.11-slim"), uses that as the
        base. Otherwise uses debian:bookworm-slim.

        SSH and tmux setup is handled at runtime in _start_sshd_in_sandbox to
        allow warning if these tools are not pre-installed in the base image.
        """
        if dockerfile is not None:
            dockerfile_contents = dockerfile.read_text()
            context_dir = dockerfile.parent
            image = build_image_from_dockerfile_contents(
                dockerfile_contents,
                context_dir=context_dir,
                is_each_layer_cached=True,
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

        Checks for sshd and tmux. If either is missing, logs a warning and
        installs via apt. This allows users to pre-configure their base images
        for faster startup while supporting images without these tools.
        """
        # Check if sshd is installed
        sshd_check = sandbox.exec("sh", "-c", "test -x /usr/sbin/sshd && echo yes || echo no")
        is_sshd_installed = sshd_check.stdout.read().strip() == "yes"

        # Check if tmux is installed
        tmux_check = sandbox.exec("sh", "-c", "command -v tmux >/dev/null 2>&1 && echo yes || echo no")
        is_tmux_installed = tmux_check.stdout.read().strip() == "yes"

        # Check if curl is installed
        curl_check = sandbox.exec("sh", "-c", "command -v curl >/dev/null 2>&1 && echo yes || echo no")
        is_curl_installed = curl_check.stdout.read().strip() == "yes"

        # Determine which packages need installation
        packages_to_install: list[str] = []
        if not is_sshd_installed:
            logger.warning(
                "openssh-server is not pre-installed in the base image. "
                "Installing at runtime. For faster startup, consider using an image with openssh-server pre-installed."
            )
            packages_to_install.append("openssh-server")

        if not is_tmux_installed:
            logger.warning(
                "tmux is not pre-installed in the base image. "
                "Installing at runtime. For faster startup, consider using an image with tmux pre-installed."
            )
            packages_to_install.append("tmux")

        if not is_curl_installed:
            logger.warning(
                "curl is not pre-installed in the base image. "
                "Installing at runtime. For faster startup, consider using an image with curl pre-installed."
            )
            packages_to_install.append("curl")

        # Install missing packages
        if packages_to_install:
            logger.debug("Installing packages: {}", packages_to_install)
            # Wait for apt-get commands to complete by calling .wait() on the result
            sandbox.exec("apt-get", "update", "-qq").wait()
            sandbox.exec("apt-get", "install", "-y", "-qq", *packages_to_install).wait()

        # Create sshd run directory (required for sshd to start)
        # Wait for the command to complete before proceeding
        sandbox.exec("mkdir", "-p", "/run/sshd").wait()

        # Create mngr host directory
        sandbox.exec("mkdir", "-p", str(self.host_dir)).wait()

    def _start_sshd_in_sandbox(
        self,
        sandbox: modal.Sandbox,
        client_public_key: str,
        host_private_key: str,
        host_public_key: str,
    ) -> None:
        """Set up SSH access and start sshd in the sandbox.

        This method handles the complete SSH setup including package installation
        (if needed), key configuration, and starting the sshd daemon.
        """
        # Check for required packages and install if missing
        self._check_and_install_packages(sandbox)

        # Create .ssh directory
        sandbox.exec("mkdir", "-p", "/root/.ssh").wait()

        # Write the authorized_keys file (for client authentication)
        with sandbox.open("/root/.ssh/authorized_keys", "wb") as f:
            f.write(client_public_key.encode("utf-8"))

        # Remove any existing host keys first to ensure we use our key
        # This is important for restored sandboxes which may have old keys from the snapshot
        sandbox.exec("rm", "-f", "/etc/ssh/ssh_host_*").wait()

        # Install the host key (for host identification)
        # This ensures all Modal sandboxes use the same host key that we control
        with sandbox.open("/etc/ssh/ssh_host_ed25519_key", "wb") as f:
            f.write(host_private_key.encode("utf-8"))

        with sandbox.open("/etc/ssh/ssh_host_ed25519_key.pub", "wb") as f:
            f.write(host_public_key.encode("utf-8"))

        # Set correct permissions on host key
        sandbox.exec("chmod", "600", "/etc/ssh/ssh_host_ed25519_key").wait()
        sandbox.exec("chmod", "644", "/etc/ssh/ssh_host_ed25519_key.pub").wait()

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
                cpu=self.default_cpu,
                memory=self.default_memory,
                image=None,
                dockerfile=None,
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
        parser.add_argument("--dockerfile", type=str, default=None)
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
            dockerfile=parsed.dockerfile,
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
        snapshots: list[dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        """Build the tags dict to store on a Modal sandbox.

        Uses only 3 mngr tags (host_id, host_name, host_record) to stay well
        under Modal's 10-tag limit, leaving 7 tags for user-defined tags.

        Snapshots are stored as a list of dicts in the host_record JSON blob,
        each containing: id, name, created_at (ISO format), and modal_image_id.
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
                "dockerfile": config.dockerfile,
            },
            "snapshots": snapshots if snapshots is not None else [],
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
    ) -> tuple[HostId, HostName, str, int, str | None, SandboxConfig, dict[str, str], list[dict[str, Any]]]:
        """Parse tags from a Modal sandbox into structured data.

        The returned tuple contains (host_id, name, ssh_host, ssh_port, host_public_key, config, user_tags, snapshots).
        host_public_key may be None for sandboxes created before we started storing it in tags.
        snapshots is a list of dicts containing snapshot metadata.
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
            dockerfile=config_data.get("dockerfile"),
            timeout=int(config_data.get("timeout", self.default_timeout)),
        )

        # Extract snapshots list from host record
        snapshots: list[dict[str, Any]] = host_record.get("snapshots", [])

        # Extract user tags (those with the user prefix)
        user_tags: dict[str, str] = {}
        for key, value in tags.items():
            if key.startswith(TAG_USER_PREFIX):
                user_key = key[len(TAG_USER_PREFIX) :]
                user_tags[user_key] = value

        return host_id, name, ssh_host, ssh_port, host_public_key, config, user_tags, snapshots

    def _get_modal_app(self) -> modal.App:
        """Get or create the Modal app for this provider instance with output capture.

        Creates an ephemeral app with `modal.App(name)` and enters its `app.run()`
        context manager. The app is cached in a module-level registry by name, so
        multiple ModalProviderInstance objects with the same app_name will share
        the same app instance.

        Modal output is captured via enable_modal_output_capture(), which routes
        all Modal logs to both a StringIO buffer (for inspection) and to loguru
        (for mngr's logging system). This enables detection of build failures and
        other issues that would otherwise be difficult to identify.

        The context is exited when `close()` is called, making the app ephemeral
        and preventing accumulation of apps (which can hit Modal's limits).

        Raises modal.exception.AuthError if Modal credentials are not configured.
        """
        if self.app_name in _app_registry:
            app, _ = _app_registry[self.app_name]
            return app

        logger.debug("Creating ephemeral Modal app with output capture: {}", self.app_name)

        # Enter the output capture context first
        output_capture_context = enable_modal_output_capture(is_logging_to_loguru=True)
        output_buffer, loguru_writer = output_capture_context.__enter__()

        # Create the Modal app
        app = modal.App(self.app_name)

        # Enter the app.run() context manager manually so we can return the app
        # while keeping the context active until close() is called
        run_context = app.run()
        run_context.__enter__()

        # Set app metadata on the loguru writer for structured logging
        if loguru_writer is not None:
            loguru_writer.app_id = app.app_id
            loguru_writer.app_name = app.name

        context_handle = _ModalAppContextHandle(
            run_context=run_context,
            app_name=self.app_name,
            output_capture_context=output_capture_context,
            output_buffer=output_buffer,
            loguru_writer=loguru_writer,
        )
        _app_registry[self.app_name] = (app, context_handle)
        return app

    def get_captured_output(self) -> str:
        """Get all captured Modal output for this provider instance.

        Returns the contents of the output buffer that has been capturing Modal
        logs since the app was created. This can be used to detect build failures
        or other issues by inspecting the captured output.

        Returns an empty string if no app has been created yet.
        """
        if self.app_name not in _app_registry:
            return ""
        _, context_handle = _app_registry[self.app_name]
        return context_handle.output_buffer.getvalue()

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
        host_id, name, ssh_host, ssh_port, host_public_key, config, user_tags, snapshots = self._parse_sandbox_tags(
            tags
        )

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

        # Parse build arguments (including --dockerfile if specified)
        config = self._parse_build_args(build_args)
        base_image = str(image) if image else config.image
        dockerfile_path = Path(config.dockerfile) if config.dockerfile else None

        # Get SSH client keypair (for authentication)
        private_key_path, client_public_key = self._get_ssh_keypair()
        logger.debug("Using SSH client key: {}", private_key_path)

        # Get SSH host keypair (for host identification)
        host_key_path, host_public_key = self._get_host_keypair()
        host_private_key = host_key_path.read_text()
        logger.debug("Using SSH host key: {}", host_key_path)

        # Build the Modal image
        logger.debug("Building Modal image...")
        modal_image = self._build_modal_image(base_image, dockerfile_path)

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

        # Load snapshot data from local storage
        snapshot_full_data = self._load_snapshot_locally(host_id, snapshot_id)
        if snapshot_full_data is None:
            raise SnapshotNotFoundError(snapshot_id)

        snapshot_data = snapshot_full_data["snapshot"]
        host_metadata = snapshot_full_data["host"]
        modal_image_id = snapshot_data.get("modal_image_id")

        if not modal_image_id:
            raise MngrError(f"Snapshot {snapshot_id} does not contain a Modal image ID for restoration.")

        logger.info("Restoring Modal sandbox from snapshot: host_id={}, snapshot_id={}", host_id, snapshot_id)

        # Get SSH keypairs
        private_key_path, client_public_key = self._get_ssh_keypair()
        host_key_path, host_public_key = self._get_host_keypair()
        host_private_key = host_key_path.read_text()

        # Restore sandbox configuration from snapshot metadata
        config_data = host_metadata.get("config", {})
        config = SandboxConfig(
            cpu=float(config_data.get("cpu", self.default_cpu)),
            memory=float(config_data.get("memory", self.default_memory)),
            timeout=int(config_data.get("timeout", self.default_timeout)),
            gpu=config_data.get("gpu"),
            image=config_data.get("image"),
            dockerfile=config_data.get("dockerfile"),
        )
        host_name = HostName(host_metadata.get("host_name", f"restored-{str(host_id)[-8:]}"))
        user_tags: dict[str, str] = host_metadata.get("user_tags", {})

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
            )
        else:
            new_sandbox = modal.Sandbox.create(
                image=modal_image,
                app=app,
                timeout=config.timeout,
                cpu=config.cpu,
                memory=memory_mb,
                unencrypted_ports=[CONTAINER_SSH_PORT],
            )
        logger.info("Created sandbox from snapshot: {}", new_sandbox.object_id)

        # Start sshd
        self._start_sshd_in_sandbox(new_sandbox, client_public_key, host_private_key, host_public_key)

        # Get SSH connection info
        ssh_host, ssh_port = self._get_ssh_info_from_sandbox(new_sandbox)

        # Add to known hosts
        add_host_to_known_hosts(self._known_hosts_path, ssh_host, ssh_port, host_public_key)

        # Wait for sshd
        self._wait_for_sshd(ssh_host, ssh_port)

        # Store metadata as tags (preserving the original host_id)
        sandbox_tags = self._build_sandbox_tags(
            host_id=host_id,
            name=host_name,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            host_public_key=host_public_key,
            config=config,
            user_tags=user_tags,
        )
        new_sandbox.set_tags(sandbox_tags)

        # Create pyinfra host and return
        pyinfra_host = self._create_pyinfra_host(ssh_host, ssh_port, private_key_path)
        connector = PyinfraConnector(pyinfra_host)

        restored_host = Host(
            id=host_id,
            connector=connector,
            provider_instance=self,
            mngr_ctx=self.mngr_ctx,
        )

        logger.info("Restored Modal host from snapshot: id={}, name={}", host_id, host_name)
        return restored_host

    def destroy_host(
        self,
        host: HostInterface | HostId,
        delete_snapshots: bool = True,
    ) -> None:
        """Destroy a Modal sandbox permanently.

        If delete_snapshots is True, also deletes local snapshot metadata files.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        self.stop_host(host)

        if delete_snapshots:
            self._delete_all_snapshots_locally(host_id)

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
    # Snapshot Methods
    # =========================================================================

    def _update_sandbox_snapshots(
        self,
        sandbox: modal.Sandbox,
        snapshots: list[dict[str, Any]],
    ) -> None:
        """Update the snapshots list in a sandbox's tags."""
        tags = sandbox.get_tags()
        host_record = json.loads(tags[TAG_HOST_RECORD])
        host_record["snapshots"] = snapshots
        tags[TAG_HOST_RECORD] = json.dumps(host_record)
        sandbox.set_tags(tags)

    def create_snapshot(
        self,
        host: HostInterface | HostId,
        name: SnapshotName | None = None,
    ) -> SnapshotId:
        """Create a snapshot of a Modal sandbox's filesystem.

        Uses Modal's sandbox.snapshot_filesystem() to create an incremental snapshot.
        Snapshot metadata is stored both in the sandbox's tags and locally on disk.
        Local storage allows restoration even after the original sandbox is terminated.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.debug("Creating snapshot for Modal sandbox: host_id={}", host_id)

        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is None:
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

        snapshot_data: dict[str, Any] = {
            "id": str(snapshot_id),
            "name": str(snapshot_name),
            "created_at": created_at.isoformat(),
            "modal_image_id": modal_image_id,
        }

        # Read existing snapshots and host metadata for local storage
        tags = sandbox.get_tags()
        parsed_host_id, host_name, ssh_host, ssh_port, host_public_key, config, user_tags, existing_snapshots = (
            self._parse_sandbox_tags(tags)
        )
        updated_snapshots = existing_snapshots + [snapshot_data]

        # Update the sandbox tags with the new snapshot list
        self._update_sandbox_snapshots(sandbox, updated_snapshots)

        # Save snapshot locally with host metadata for restoration after termination
        host_metadata: dict[str, Any] = {
            "host_id": str(host_id),
            "host_name": str(host_name),
            "config": {
                "cpu": config.cpu,
                "memory": config.memory,
                "timeout": config.timeout,
                "gpu": config.gpu,
                "image": config.image,
                "dockerfile": config.dockerfile,
            },
            "user_tags": user_tags,
        }
        self._save_snapshot_locally(host_id, snapshot_data, host_metadata)

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

        Reads snapshot metadata from sandbox tags if the sandbox is running,
        or from local storage if the sandbox has been terminated.
        """
        host_id = host.id if isinstance(host, HostInterface) else host

        # Try to get snapshots from sandbox tags first
        snapshots_data: list[dict[str, Any]] = []
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            tags = sandbox.get_tags()
            try:
                _, _, _, _, _, _, _, snapshots_data = self._parse_sandbox_tags(tags)
            except (KeyError, ValueError):
                pass

        # Fall back to local storage if sandbox is gone or has no snapshots
        if not snapshots_data:
            snapshots_data = self._list_snapshots_locally(host_id)

        # Convert to SnapshotInfo objects, sorted by created_at (newest first)
        snapshots: list[SnapshotInfo] = []
        for idx, snap_data in enumerate(reversed(snapshots_data)):
            created_at_str = snap_data.get("created_at")
            created_at = datetime.fromisoformat(created_at_str) if created_at_str else datetime.now(timezone.utc)
            snapshots.append(
                SnapshotInfo(
                    id=SnapshotId(snap_data["id"]),
                    name=SnapshotName(snap_data.get("name", "")),
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

        Removes the snapshot metadata from both sandbox tags (if running) and
        local storage. Note that the underlying Modal image is not deleted
        since Modal doesn't yet provide a way to delete images via their API;
        they will be garbage-collected by Modal when no longer referenced.
        """
        host_id = host.id if isinstance(host, HostInterface) else host
        logger.debug("Deleting snapshot {} from Modal sandbox: host_id={}", snapshot_id, host_id)

        found = False

        # Try to remove from sandbox tags if sandbox is still running
        sandbox = self._find_sandbox_by_host_id(host_id)
        if sandbox is not None:
            tags = sandbox.get_tags()
            try:
                _, _, _, _, _, _, _, existing_snapshots = self._parse_sandbox_tags(tags)
                snapshot_id_str = str(snapshot_id)
                updated_snapshots = [s for s in existing_snapshots if s.get("id") != snapshot_id_str]

                if len(updated_snapshots) < len(existing_snapshots):
                    found = True
                    self._update_sandbox_snapshots(sandbox, updated_snapshots)
            except (KeyError, ValueError):
                pass

        # Also remove from local storage
        local_snapshot = self._load_snapshot_locally(host_id, snapshot_id)
        if local_snapshot is not None:
            found = True
            self._delete_snapshot_locally(host_id, snapshot_id)

        if not found:
            raise SnapshotNotFoundError(snapshot_id)

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
