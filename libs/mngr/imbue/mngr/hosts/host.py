from __future__ import annotations

import fcntl
import io
import json
import os
import shlex
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import IO
from typing import Iterator
from typing import Mapping
from typing import Sequence
from typing import cast

from loguru import logger
from paramiko import SSHException
from pydantic import Field
from pydantic import ValidationError
from pyinfra.api.command import StringCommand
from pyinfra.connectors.util import CommandOutput

from imbue.imbue_common.errors import SwitchError
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.agents.agent_registry import resolve_agent_type
from imbue.mngr.agents.base_agent import BaseAgent
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import AgentNotFoundOnHostError
from imbue.mngr.errors import AgentStartError
from imbue.mngr.errors import HostConnectionError
from imbue.mngr.errors import HostDataSchemaError
from imbue.mngr.errors import InvalidActivityTypeError
from imbue.mngr.errors import LockNotHeldError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.errors import UserInputError
from imbue.mngr.hosts.common import LOCAL_CONNECTOR_NAME
from imbue.mngr.hosts.common import is_macos
from imbue.mngr.hosts.offline_host import BaseHost
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CertifiedHostData
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.data_types import FileTransferSpec
from imbue.mngr.interfaces.data_types import HostResources
from imbue.mngr.interfaces.data_types import PyinfraConnector
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import NamedCommand
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import WorkDirCopyMode
from imbue.mngr.utils.env_utils import parse_env_file
from imbue.mngr.utils.git_utils import get_current_git_branch


class HostLocation(FrozenModel):
    """A path on a specific host."""

    host: OnlineHostInterface = Field(
        description="The actual host where the source resides",
    )
    path: Path = Field(
        description="The actual path to the source directory on the host",
    )


class Host(BaseHost, OnlineHostInterface):
    """Host implementation that proxies operations through a pyinfra connector.

    All operations (command execution, file read/write) are performed through
    the pyinfra connector, which handles both local and remote hosts transparently.
    """

    connector: PyinfraConnector = Field(frozen=True, description="Pyinfra connector for host operations")
    provider_instance: ProviderInstanceInterface = Field(
        frozen=True, description="The provider instance managing this host"
    )
    mngr_ctx: MngrContext = Field(frozen=True, repr=False, description="The mngr context")

    @property
    def is_local(self) -> bool:
        """Check if this host uses the local connector."""
        return self.connector.connector_cls_name == LOCAL_CONNECTOR_NAME

    def get_name(self) -> HostName:
        """Return the human-readable name of this host."""
        return HostName(self.connector.name)

    # =========================================================================
    # Core Primitives (pyinfra-compatible signatures)
    # =========================================================================

    def _ensure_connected(self) -> None:
        """Ensure the pyinfra host is connected."""
        if not self.connector.host.connected:
            self.connector.host.connect(raise_exceptions=True)

    def disconnect(self) -> None:
        """Disconnect the pyinfra host if connected.

        This should be called before destroying or stopping a host to cleanly
        close the SSH connection. Failure to disconnect can lead to stale
        socket state causing "Socket is closed" errors in subsequent operations.
        """
        if self.connector.host.connected:
            logger.trace("Disconnecting pyinfra host {}", self.id)
            self.connector.host.disconnect()

    def _run_shell_command(
        self,
        command: StringCommand,
        *,
        _timeout: int | None = None,
        _success_exit_codes: tuple[int, ...] | None = None,
        _env: dict[str, str] | None = None,
        _chdir: str | None = None,
        _shell_executable: str = "sh",
        # Su config
        _su_user: str | None = None,
        _use_su_login: bool = False,
        _su_shell: str | None = None,
        _preserve_su_env: bool = False,
        # Sudo config
        _sudo: bool = False,
        _sudo_user: str | None = None,
        _use_sudo_login: bool = False,
        _sudo_password: str = "",
        _sudo_askpass_path: str | None = None,
        _preserve_sudo_env: bool = False,
        # Doas config
        _doas: bool = False,
        _doas_user: str | None = None,
        # Retry config
        _retries: int = 0,
        _retry_delay: int = 0,
        _retry_until: str | None = None,
    ) -> tuple[bool, CommandOutput]:
        """
        Execute a shell command on the host.

        This is an internal-only method, in case you need to do something fancy

        Prefer using execute_command() instead whenever possible.
        """
        try:
            self._ensure_connected()
            return self.connector.host.run_shell_command(
                command,
                _timeout=_timeout,
                _success_exit_codes=_success_exit_codes,
                _env=_env,
                _chdir=_chdir,
                _shell_executable=_shell_executable,
                _su_user=_su_user,
                _use_su_login=_use_su_login,
                _su_shell=_su_shell,
                _preserve_su_env=_preserve_su_env,
                _sudo=_sudo,
                _sudo_user=_sudo_user,
                _use_sudo_login=_use_sudo_login,
                _sudo_password=_sudo_password,
                _sudo_askpass_path=_sudo_askpass_path,
                _preserve_sudo_env=_preserve_sudo_env,
                _doas=_doas,
                _doas_user=_doas_user,
                _retries=_retries,
                _retry_delay=_retry_delay,
                _retry_until=_retry_until,
            )
        except OSError as e:
            if "Socket is closed" in str(e):
                # FIXME: these two lines are duplicated everywhere (on_connection_error and raise HostConnectionError)
                #  Please instead refactor this so that we simply raise, and each of these 3 methods that are raising have
                #  a decorator that handles the calling of on_connection_error automatically
                self.provider_instance.on_connection_error(self.id)
                raise HostConnectionError("Connection was closed while running command") from e
            else:
                raise
        except (EOFError, SSHException) as e:
            self.provider_instance.on_connection_error(self.id)
            raise HostConnectionError("Could not execute command due to connection error") from e

    def _get_file(
        self,
        remote_filename: str,
        filename_or_io: str | IO[bytes],
        remote_temp_filename: str | None = None,
    ) -> bool:
        """Read a file from the host.

        This is an internal-only method, in case you need to do something fancy

        Prefer using read_file() instead whenever possible.

        Raises FileNotFoundError if the remote file does not exist.
        """
        try:
            self._ensure_connected()
            try:
                return self.connector.host.get_file(
                    remote_filename,
                    filename_or_io,
                    remote_temp_filename=remote_temp_filename,
                )
            except OSError as e:
                # pyinfra raises OSError for missing files - convert to FileNotFoundError
                error_msg = str(e)
                if "No such file or directory" in error_msg or "cannot stat" in error_msg:
                    raise FileNotFoundError(f"File not found: {remote_filename}") from e
                elif "Socket is closed" in str(e):
                    self.provider_instance.on_connection_error(self.id)
                    raise HostConnectionError("Connection was closed while reading file") from e
                else:
                    raise
        except (EOFError, SSHException) as e:
            self.provider_instance.on_connection_error(self.id)
            raise HostConnectionError("Could not read file due to connection error") from e

    def _put_file(
        self,
        filename_or_io: str | IO[str] | IO[bytes],
        remote_filename: str,
        remote_temp_filename: str | None = None,
    ) -> bool:
        """Write a file to the host.

        This is an internal-only method, in case you need to do something fancy

        Prefer using write_file() or write_text_file() instead whenever possible.
        """
        try:
            self._ensure_connected()
            return self.connector.host.put_file(
                filename_or_io,
                remote_filename,
                remote_temp_filename=remote_temp_filename,
            )
        except OSError as e:
            if "Socket is closed" in str(e):
                self.provider_instance.on_connection_error(self.id)
                raise HostConnectionError("Connection was closed while writing file") from e
            else:
                raise
        except (EOFError, SSHException) as e:
            self.provider_instance.on_connection_error(self.id)
            raise HostConnectionError("Could not write file due to connection error") from e

    # =========================================================================
    # Convenience methods (built on core primitives)
    # =========================================================================

    def execute_command(
        self,
        command: str,
        user: str | None = None,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        """Execute a command and return the result."""
        logger.debug("Executing command on host {}: {}", self.id, command)
        logger.trace("Command details: user={}, cwd={}, env={}, timeout={}", user, cwd, env, timeout_seconds)
        success, output = self._run_shell_command(
            StringCommand(command),
            _su_user=user,
            _chdir=str(cwd) if cwd else None,
            _env=dict(env) if env else None,
            _timeout=int(timeout_seconds) if timeout_seconds else None,
        )
        return CommandResult(
            stdout=output.stdout,
            stderr=output.stderr,
            success=success,
        )

    def read_file(self, path: Path) -> bytes:
        """Read a file and return its contents as bytes.

        Raises FileNotFoundError if the file does not exist.
        """
        # this shortcut reduces the number of file descriptors opened on local hosts and speeds things up considerably
        if self.is_local:
            return path.read_bytes()
        else:
            output = io.BytesIO()
            self._get_file(str(path), output)
            return output.getvalue()

    def write_file(self, path: Path, content: bytes, mode: str | None = None) -> None:
        """Write bytes content to a file, creating parent directories as needed."""
        # Try to write first, only create parent directory if the write fails.
        # This avoids an extra subprocess call for mkdir -p on every write.
        if self.is_local:
            try:
                path.write_bytes(content)
            except FileNotFoundError:
                # Parent directory doesn't exist, create it and retry
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        else:
            try:
                is_success = self._put_file(io.BytesIO(content), str(path))
            except IOError:
                # pyinfra/paramiko raises IOError when the parent directory doesn't exist
                is_success = False
            if not is_success:
                # May have failed because parent directory doesn't exist, create it and retry
                parent_dir = str(path.parent)
                result = self.execute_command(f"mkdir -p '{parent_dir}'")
                if not result.success:
                    raise MngrError(
                        f"Failed to create parent directory '{parent_dir}' on host {self.id} because: {result.stderr}"
                    )
                is_success = self._put_file(io.BytesIO(content), str(path))
                if not is_success:
                    raise MngrError(f"Failed to write file '{str(path)}' on host {self.id}'")
        if mode is not None:
            self.execute_command(f"chmod {mode} '{str(path)}'")

    def read_text_file(self, path: Path, encoding: str = "utf-8") -> str:
        """Read a file and return its contents as a string.

        Raises FileNotFoundError if the file does not exist.
        """
        return self.read_file(path).decode(encoding)

    def write_text_file(
        self,
        path: Path,
        content: str,
        encoding: str = "utf-8",
        mode: str | None = None,
    ) -> None:
        """Write string content to a file, creating parent directories as needed."""
        self.write_file(path, content.encode(encoding), mode=mode)

    def _get_file_mtime(self, path: Path) -> datetime | None:
        """Get the mtime of a file on the host."""
        if self.is_local:
            try:
                mtime = path.stat().st_mtime
                return datetime.fromtimestamp(mtime, tz=timezone.utc)
            except (FileNotFoundError, OSError):
                return None
        result = self.execute_command(f"stat -c %Y '{str(path)}' 2>/dev/null || stat -f %m '{str(path)}' 2>/dev/null")
        if result.success and result.stdout.strip():
            try:
                mtime = int(result.stdout.strip())
                return datetime.fromtimestamp(mtime, tz=timezone.utc)
            except ValueError:
                pass
        return None

    def get_file_mtime(self, path: Path) -> datetime | None:
        """Return the modification time of a file, or None if the file doesn't exist."""
        return self._get_file_mtime(path)

    def _path_exists(self, path: Path) -> bool:
        """Check if a path exists on the host."""
        if self.is_local:
            return path.exists()
        result = self.execute_command(f"test -e '{str(path)}'")
        return result.success

    def _is_directory(self, path: Path) -> bool:
        """Check if a path is a directory on the host."""
        if self.is_local:
            return path.is_dir()
        result = self.execute_command(f"test -d '{str(path)}'")
        return result.success

    def _list_directory(self, path: Path) -> list[str]:
        """List files in a directory on the host."""
        if self.is_local:
            try:
                return list(entry.name for entry in path.iterdir())
            except (FileNotFoundError, OSError):
                return []
        result = self.execute_command(f"ls -1 '{str(path)}' 2>/dev/null")
        if result.success and result.stdout.strip():
            return result.stdout.strip().split("\n")
        return []

    def _remove_directory(self, path: Path) -> None:
        """Remove a directory and its contents on the host."""
        self.execute_command(f"rm -rf '{str(path)}'")

    def _mkdir(self, path: Path) -> None:
        """Create a directory on the host."""
        self.execute_command(f"mkdir -p '{str(path)}'")

    def _mkdirs(self, paths: Sequence[Path]) -> None:
        """Create multiple directories on the host."""
        joined_dirs = " ".join(f"'{str(p)}'" for p in paths)
        self.execute_command(f"mkdir -p {joined_dirs}")

    def _get_ssh_connection_info(self) -> tuple[str, str, int, Path] | None:
        """Get SSH connection info for this host if it's remote.

        Returns (user, hostname, port, private_key_path) if remote, None if local.
        """
        if self.is_local:
            return None

        host_data = self.connector.host.data
        user = host_data.get("ssh_user", "root")
        hostname = self.connector.host.name
        port = host_data.get("ssh_port", 22)
        key_path_str = host_data.get("ssh_key", "")
        assert key_path_str, "SSH key path must be set for remote hosts"

        return (user, hostname, port, Path(key_path_str))

    # =========================================================================
    # Activity Times
    # =========================================================================

    def get_reported_activity_time(self, activity_type: ActivitySource) -> datetime | None:
        """Get the last reported activity time for the given type."""
        activity_path = self.host_dir / "activity" / activity_type.value.lower()
        return self._get_file_mtime(activity_path)

    def record_activity(self, activity_type: ActivitySource) -> None:
        """Record activity by writing JSON with timestamp and metadata.

        Only BOOT is valid for host-level activity.

        The JSON contains:
        - time: milliseconds since Unix epoch (int)
        - host_id: the host's ID (for debugging)

        Note: The authoritative activity time is the file's mtime, not the
        JSON content. The JSON is for debugging/auditing purposes.
        """
        if activity_type != ActivitySource.BOOT:
            raise InvalidActivityTypeError(f"Only BOOT activity can be recorded on host, got: {activity_type}")

        logger.trace("Recording {} activity on host {}", activity_type, self.id)
        activity_path = self.host_dir / "activity" / activity_type.value.lower()
        now = datetime.now(timezone.utc)
        data = {
            "time": int(now.timestamp() * 1000),
            "host_id": str(self.id),
        }
        self.write_text_file(activity_path, json.dumps(data, indent=2))

    def get_reported_activity_content(self, activity_type: ActivitySource) -> str | None:
        """Get the content of the activity file."""
        activity_path = self.host_dir / "activity" / activity_type.value.lower()
        try:
            return self.read_text_file(activity_path)
        except FileNotFoundError:
            return None

    # =========================================================================
    # Cooperative Locking
    # =========================================================================

    @contextmanager
    def lock_cooperatively(self, timeout_seconds: float = 300.0) -> Iterator[None]:
        """Context manager for acquiring and releasing the host lock.

        TODO: Implement remote locking mechanism (e.g., via lock files with PIDs).
        Currently only works for local hosts.
        """
        lock_file_path = self.host_dir / "host_lock"

        if not self.is_local:
            # this is obviously not yet right--we're just making the host lock so that the shutdown script doesnt trigger while creating a host
            self.write_text_file(lock_file_path, str(time.time()))
            yield
            self.execute_command("rm -f '{}'".format(str(lock_file_path)))
            return

        lock_file_path.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        elapsed_time = 0.0

        logger.debug("Acquiring host lock at {}", lock_file_path)
        lock_file = open(str(lock_file_path), "w")
        try:
            while elapsed_time <= timeout_seconds:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.trace("Lock acquired after {:.2f}s", time.time() - start_time)
                    break
                except BlockingIOError:
                    time.sleep(0.1)
                    elapsed_time = time.time() - start_time
            else:
                raise LockNotHeldError(f"Failed to acquire lock within {timeout_seconds}s")

            yield
        finally:
            logger.trace("Releasing host lock")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()

    def get_reported_lock_time(self) -> datetime | None:
        """Get the mtime of the lock file."""
        lock_path = self.host_dir / "host_lock"
        return self._get_file_mtime(lock_path)

    # =========================================================================
    # Certified Data
    # =========================================================================

    def get_certified_data(self) -> CertifiedHostData:
        """Get all certified data from data.json."""
        data_path = self.host_dir / "data.json"
        try:
            content = self.read_text_file(data_path)
            data = json.loads(content)
            return CertifiedHostData(**data)
        except FileNotFoundError:
            return CertifiedHostData(
                host_id=str(self.id),
                host_name=str(self.get_name()),
            )
        except ValidationError as e:
            raise HostDataSchemaError(str(data_path), str(e)) from e

    def set_certified_data(self, data: CertifiedHostData) -> None:
        """Save certified data to data.json and notify the provider."""
        data_path = self.host_dir / "data.json"
        self.write_text_file(data_path, json.dumps(data.model_dump(by_alias=True), indent=2))
        # Notify the provider so it can update any external storage (e.g., Modal volume)
        if self.on_updated_host_data:
            self.on_updated_host_data(self.id, data)

    def _add_generated_work_dir(self, work_dir: Path) -> None:
        """Add a work directory to the list of generated work directories."""
        certified_data = self.get_certified_data()
        existing_dirs = set(certified_data.generated_work_dirs)
        existing_dirs.add(str(work_dir))
        updated_data = certified_data.model_copy(update={"generated_work_dirs": tuple(sorted(existing_dirs))})
        self.set_certified_data(updated_data)

    def _remove_generated_work_dir(self, work_dir: Path) -> None:
        """Remove a work directory from the list of generated work directories."""
        certified_data = self.get_certified_data()
        existing_dirs = set(certified_data.generated_work_dirs)
        existing_dirs.discard(str(work_dir))
        updated_data = certified_data.model_copy(update={"generated_work_dirs": tuple(sorted(existing_dirs))})
        self.set_certified_data(updated_data)

    def _is_generated_work_dir(self, work_dir: Path) -> bool:
        """Check if a work directory was generated by mngr."""
        certified_data = self.get_certified_data()
        return str(work_dir) in certified_data.generated_work_dirs

    def set_plugin_data(self, plugin_name: str, data: dict[str, Any]) -> None:
        """Set certified plugin data in data.json."""
        certified_data = self.get_certified_data()
        updated_plugin = dict(certified_data.plugin)
        updated_plugin[plugin_name] = data

        updated_data = certified_data.model_copy(update={"plugin": updated_plugin})
        self.set_certified_data(updated_data)

    # =========================================================================
    # Reported Plugin Data
    # =========================================================================

    def get_reported_plugin_state_file_data(self, plugin_name: str, filename: str) -> str:
        """Get a reported plugin state file."""
        plugin_path = self.host_dir / "plugin" / plugin_name / filename
        return self.read_text_file(plugin_path)

    def set_reported_plugin_state_file_data(
        self,
        plugin_name: str,
        filename: str,
        data: str,
    ) -> None:
        """Set a reported plugin state file."""
        plugin_path = self.host_dir / "plugin" / plugin_name / filename
        self.write_text_file(plugin_path, data)

    def get_reported_plugin_state_files(self, plugin_name: str) -> list[str]:
        """List all plugin state files."""
        plugin_dir = self.host_dir / "plugin" / plugin_name
        if not self._is_directory(plugin_dir):
            return []
        return self._list_directory(plugin_dir)

    # =========================================================================
    # Environment
    # =========================================================================

    def get_env_vars(self) -> dict[str, str]:
        """Get all environment variables from the host env file."""
        env_path = self.host_dir / "env"
        try:
            content = self.read_text_file(env_path)
            return parse_env_file(content)
        except FileNotFoundError:
            return {}

    def set_env_vars(self, env: Mapping[str, str]) -> None:
        """Set all environment variables in the host env file."""
        env_path = self.host_dir / "env"
        content = _format_env_file(env)
        self.write_text_file(env_path, content)

    def get_env_var(self, key: str) -> str | None:
        """Get a single environment variable."""
        env_vars = self.get_env_vars()
        return env_vars.get(key)

    def set_env_var(self, key: str, value: str) -> None:
        """Set a single environment variable."""
        env_vars = self.get_env_vars()
        env_vars[key] = value
        self.set_env_vars(env_vars)

    # =========================================================================
    # Provider-Derived Information
    # =========================================================================

    def get_seconds_since_stopped(self) -> float | None:
        """Return the number of seconds since this host was stopped (or None if it is running)."""
        return None

    def get_stop_time(self) -> datetime | None:
        """Return the host last stop time as a datetime, or None if unknown."""
        return None

    # FIXME: both this and the below method will be broken if we ever have remote hosts that are OSX
    #  instead of this, we should, for each of them, make a single command that does the platform check before dispatching to the resulting platform-dependent logic
    def get_uptime_seconds(self) -> float:
        """Get host uptime in seconds."""
        if is_macos() and self.is_local:
            # macOS: use sysctl kern.boottime to get boot time, then compute uptime
            # Output format: { sec = 1234567890, usec = 123456 } ...
            # Use awk to reliably extract the sec value (not usec)
            result = self.execute_command(
                "sysctl -n kern.boottime 2>/dev/null | awk -F'[ ,=]+' '{for(i=1;i<=NF;i++) if($i==\"sec\") print $(i+1)}' && date +%s"
            )
            if result.success:
                output_lines = result.stdout.strip().split("\n")
                if len(output_lines) == 2:
                    boot_time = int(output_lines[0])
                    current_time = int(output_lines[1])
                    return float(current_time - boot_time)
        else:
            # Linux: use /proc/uptime
            result = self.execute_command("cat /proc/uptime 2>/dev/null")
            if result.success:
                uptime_str = result.stdout.split()[0]
                return float(uptime_str)

        return 0.0

    def get_boot_time(self) -> datetime | None:
        """Get the host boot time as a datetime.

        Returns the actual boot time from the OS, not computed from uptime,
        to avoid timing inconsistencies.
        """
        if is_macos() and self.is_local:
            # macOS: use sysctl kern.boottime which gives boot time directly
            # Output format: { sec = 1234567890, usec = 123456 } ...
            # Use awk to reliably extract the sec value (not usec)
            result = self.execute_command(
                "sysctl -n kern.boottime 2>/dev/null | awk -F'[ ,=]+' '{for(i=1;i<=NF;i++) if($i==\"sec\") print $(i+1)}'"
            )
            if result.success:
                try:
                    boot_timestamp = int(result.stdout.strip())
                    return datetime.fromtimestamp(boot_timestamp, tz=timezone.utc)
                except (ValueError, OSError):
                    pass
        else:
            # Linux: use /proc/stat which has btime (boot time as Unix timestamp)
            result = self.execute_command("grep '^btime ' /proc/stat 2>/dev/null | awk '{print $2}'")
            if result.success:
                try:
                    boot_timestamp = int(result.stdout.strip())
                    return datetime.fromtimestamp(boot_timestamp, tz=timezone.utc)
                except (ValueError, OSError):
                    pass

        return None

    def get_provider_resources(self) -> HostResources:
        """Get resources from the provider."""
        return self.provider_instance.get_host_resources(self)

    def set_tags(self, tags: Mapping[str, str]) -> None:
        """Set tags via the provider."""
        logger.trace("Setting {} tag(s) on host {}", len(tags), self.id)
        self.provider_instance.set_host_tags(self, tags)

    def add_tags(self, tags: Mapping[str, str]) -> None:
        """Add tags via the provider."""
        self.provider_instance.add_tags_to_host(self, tags)

    def remove_tags(self, keys: Sequence[str]) -> None:
        """Remove tags by key via the provider."""
        self.provider_instance.remove_tags_from_host(self, keys)

    # =========================================================================
    # Agent Information
    # =========================================================================

    def save_agent_data(self, agent_id: AgentId, agent_data: Mapping[str, object]) -> None:
        """Persist agent data to external storage via the provider."""
        self.provider_instance.persist_agent_data(self.id, agent_data)

    def get_agents(self) -> list[AgentInterface]:
        """Get all agents on this host."""
        logger.trace("Loading agents from host {}", self.id)
        agents_dir = self.host_dir / "agents"
        if not self._is_directory(agents_dir):
            logger.trace("No agents directory found for host {}", self.id)
            return []

        agents: list[AgentInterface] = []
        for agent_id_str in self._list_directory(agents_dir):
            agent_dir = agents_dir / agent_id_str
            if self._is_directory(agent_dir):
                agent = self._load_agent_from_dir(agent_dir)
                if agent is not None:
                    agents.append(agent)
        logger.trace("Loaded {} agent(s) from host {}", len(agents), self.id)
        return agents

    def get_agent_references(self) -> list[AgentReference]:
        """Get lightweight references to all agents on this host.

        This method reads only the data.json files for each agent, avoiding the
        overhead of fully loading agent objects. The certified_data field contains
        the full data.json contents.

        Note that we override the base method in order to read more directly from the host,
        since that data is more likely to be up-to-date.
        """
        logger.trace("Loading agent references from host {}", self.id)
        agents_dir = self.host_dir / "agents"
        if not self._is_directory(agents_dir):
            logger.trace("No agents directory found for host {}", self.id)
            return []

        agent_refs: list[AgentReference] = []
        for dir_name in self._list_directory(agents_dir):
            agent_dir = agents_dir / dir_name
            if self._is_directory(agent_dir):
                data_path = agent_dir / "data.json"
                try:
                    content = self.read_text_file(data_path)
                except FileNotFoundError:
                    logger.warning("Could not load agent reference from {}", data_path)
                    continue
                try:
                    data = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning("Could not load agent reference from {} because json was invalid: {}", data_path, e)
                    continue
                ref = self._validate_and_create_agent_reference(data)
                if ref is not None:
                    agent_refs.append(ref)

        logger.trace("Loaded {} agent reference(s) from host {}", len(agent_refs), self.id)
        return agent_refs

    def _load_agent_from_dir(self, agent_dir: Path) -> AgentInterface | None:
        """Load an agent from its state directory."""
        data_path = agent_dir / "data.json"
        try:
            content = self.read_text_file(data_path)
        except FileNotFoundError:
            logger.trace("Agent data file not found at {}", data_path)
            return None

        data = json.loads(content)
        logger.trace("Loaded agent {} from {}", data.get("name"), agent_dir)

        agent_type = AgentTypeName(data["type"])
        resolved = resolve_agent_type(agent_type, self.mngr_ctx.config)

        return cast(type[BaseAgent], resolved.agent_class)(
            id=AgentId(data["id"]),
            name=AgentName(data["name"]),
            agent_type=agent_type,
            work_dir=Path(data["work_dir"]),
            create_time=datetime.fromisoformat(data["create_time"]),
            host_id=self.id,
            host=self,
            mngr_ctx=self.mngr_ctx,
            agent_config=resolved.agent_config,
        )

    def create_agent_work_dir(
        self,
        host: OnlineHostInterface,
        path: Path,
        options: CreateAgentOptions,
    ) -> Path:
        """Create the work_dir directory for a new agent."""
        copy_mode = options.git.copy_mode if options.git else WorkDirCopyMode.COPY
        logger.debug("Creating agent work directory", copy_mode=str(copy_mode))
        if copy_mode == WorkDirCopyMode.WORKTREE:
            return self._create_work_dir_as_git_worktree(host, path, options)
        elif copy_mode in (WorkDirCopyMode.COPY, WorkDirCopyMode.CLONE):
            return self._create_work_dir_as_copy(host, path, options)
        else:
            raise SwitchError(f"Unsupported work dir copy mode: {copy_mode}")

    def _create_work_dir_as_copy(
        self,
        source_host: OnlineHostInterface,
        source_path: Path,
        options: CreateAgentOptions,
    ) -> Path:
        # Check if source and target are on the same host
        source_is_same_host = source_host.id == self.id

        # If target path is specified, use it; otherwise use source path
        if options.target_path:
            target_path = options.target_path
            # If target equals source and same host, it's in-place
            is_generated_work_dir = not (source_is_same_host and source_path == target_path)
        else:
            # No target path specified, use source path directly (in-place if same host)
            target_path = source_path
            is_generated_work_dir = not source_is_same_host

        self._mkdir(target_path)

        # Track generated work directories at the host level
        if is_generated_work_dir:
            self._add_generated_work_dir(target_path)

        # If source and target are same path on same host, nothing to transfer
        if source_is_same_host and source_path == target_path:
            logger.debug("Source and target are the same path, no file transfer needed")
            return target_path

        # Check if source has a .git directory
        if source_host.is_local:
            source_has_git = (source_path / ".git").exists()
        else:
            result = source_host.execute_command(f"test -d {shlex.quote(str(source_path / '.git'))}")
            source_has_git = result.success

        # Transfer files based on whether source has .git and whether we want to include it
        is_git_synced = options.git is not None and options.git.is_git_synced
        # Exclude .git from rsync if user has specified any git options (they're making an explicit choice)
        # If options.git is None, include .git (simple file copy of everything)
        has_git_options = options.git is not None
        if is_git_synced:
            # fall back to file copy if source is not a git repo
            if not source_has_git:
                logger.warning("Source path is not a git repository, falling back to file copy")
                self._rsync_files(source_host, source_path, target_path, "--delete", exclude_git=True)
            # Source is a git repo, transfer via git
            else:
                self._transfer_git_repo(source_host, source_path, target_path, options)
                self._transfer_extra_files(source_host, source_path, target_path, options)

        # Run rsync if enabled. This is designed for adding extra files (e.g., data files not in git),
        # not for full directory sync. By default, rsync does NOT use --delete, so existing files
        # in the target won't be removed. Users can add --delete to rsync_args if they want
        # full sync behavior with file deletion.
        # Exclude .git from rsync if user specified git options (they're making an explicit choice about git handling)
        if options.data_options.is_rsync_enabled:
            self._rsync_files(
                source_host,
                source_path,
                target_path,
                extra_args=options.data_options.rsync_args,
                exclude_git=has_git_options,
            )

        return target_path

    def _transfer_git_repo(
        self,
        source_host: OnlineHostInterface,
        source_path: Path,
        target_path: Path,
        options: CreateAgentOptions,
    ) -> None:
        """Transfer a git repository from source to target."""
        new_branch_name = self._determine_branch_name(options)
        if options.git and options.git.base_branch:
            base_branch_name = options.git.base_branch
        elif source_host.is_local:
            base_branch_name = get_current_git_branch(source_path) or "main"
        else:
            result = source_host.execute_command(
                "git rev-parse --abbrev-ref HEAD",
                cwd=source_path,
            )
            base_branch_name = result.stdout.strip() if result.success else "main"

        logger.debug(
            "Transferring git repository",
            source=str(source_path),
            target=str(target_path),
            base_branch=base_branch_name,
            new_branch=new_branch_name,
        )

        # Check if target already has a .git directory
        if self.is_local:
            target_has_git = (target_path / ".git").exists()
        else:
            result = self.execute_command(f"test -d {shlex.quote(str(target_path / '.git'))}")
            target_has_git = result.success

        if target_has_git:
            logger.debug("Target already has .git")
        else:
            logger.debug("Initializing bare git repo on target")
            result = self.execute_command(
                f"git init --bare {shlex.quote(str(target_path / '.git'))} && git config --global --add safe.directory {target_path}"
            )
            if not result.success:
                raise MngrError(f"Failed to initialize git repo on target: {result.stderr}")

        self._git_push_to_target(source_host, source_path, target_path)

        logger.debug("Configuring target git repo")
        result = self.execute_command(
            f"git config --bool core.bare false && git checkout -B {shlex.quote(new_branch_name)} {shlex.quote(base_branch_name)}",
            cwd=target_path,
        )
        if not result.success:
            raise MngrError(f"Failed to configure git repo on target: {result.stderr}")

    def _git_push_to_target(
        self,
        source_host: OnlineHostInterface,
        source_path: Path,
        target_path: Path,
    ) -> None:
        """Push git repo from source to target using git push --mirror."""
        target_ssh_info = self._get_ssh_connection_info()

        if target_ssh_info is None:
            if source_host.is_local:
                git_url = str(target_path / ".git")
            else:
                source_ssh_info = source_host._get_ssh_connection_info() if isinstance(source_host, Host) else None
                if source_ssh_info is None:
                    raise MngrError("Cannot determine SSH connection info for remote source host")
                user, hostname, port, key_path = source_ssh_info
                logger.debug("Fetching from remote source to local target")
                git_ssh_cmd = f"ssh -i {shlex.quote(str(key_path))} -p {port} -o StrictHostKeyChecking=no"
                env = {"GIT_SSH_COMMAND": git_ssh_cmd}
                remote_url = f"ssh://{user}@{hostname}:{port}{source_path}/.git"
                result = subprocess.run(
                    ["git", "clone", "--mirror", remote_url, str(target_path / ".git")],
                    capture_output=True,
                    text=True,
                    env={**os.environ, **env},
                )
                if result.returncode != 0:
                    raise MngrError(f"Failed to clone from remote source: {result.stderr}")
                return
        else:
            user, hostname, port, key_path = target_ssh_info
            git_url = f"ssh://{user}@{hostname}:{port}{target_path}/.git"

        # FIXME: this whole block is a bit duplicated. Refactor to do the same thing, but assemble the args a bit more coherently
        #  For example, the reason we need --no-verify is to skip any hooks, since they can sometimes fail
        if source_host.is_local:
            logger.debug("Pushing git repo to target: {}", git_url)
            env: dict[str, str] = {}
            if target_ssh_info is not None:
                user, hostname, port, key_path = target_ssh_info
                git_ssh_cmd = f"ssh -i {shlex.quote(str(key_path))} -p {port} -o StrictHostKeyChecking=no"
                env["GIT_SSH_COMMAND"] = git_ssh_cmd

            # don't bother pushing LFS objects - they can be transferred later as needed,
            # and without this, it can take a ridiculously long time.
            env["GIT_LFS_SKIP_PUSH"] = "1"

            command_args = ["git", "-C", str(source_path), "push", "--no-verify", "--mirror", git_url]
            logger.trace(" ".join(command_args))
            logger.trace("Running git push --mirror from local source to target with env: {}", env)
            result = subprocess.run(
                command_args,
                capture_output=True,
                text=True,
                env={**os.environ, **env} if env else None,
            )
            if result.returncode != 0:
                raise MngrError(f"Failed to push git repo: {result.stderr}")
        else:
            if target_ssh_info is not None:
                user, hostname, port, key_path = target_ssh_info
                git_ssh_cmd = f"ssh -i {shlex.quote(str(key_path))} -p {port} -o StrictHostKeyChecking=no"
                result = source_host.execute_command(
                    f"GIT_SSH_COMMAND={shlex.quote(git_ssh_cmd)} git push --no-verify --mirror {shlex.quote(git_url)}",
                    cwd=source_path,
                )
            else:
                result = source_host.execute_command(
                    f"git push --no-verify --mirror {shlex.quote(git_url)}",
                    cwd=source_path,
                )
            if not result.success:
                raise MngrError(f"Failed to push git repo from remote source: {result.stderr}")

    def _transfer_extra_files(
        self,
        source_host: OnlineHostInterface,
        source_path: Path,
        target_path: Path,
        options: CreateAgentOptions,
    ) -> None:
        """Transfer extra files that aren't in git (untracked, modified, gitignored)."""
        files_to_include: list[str] = []

        is_include_unclean = options.git.is_include_unclean if options.git else True
        if is_include_unclean:
            if source_host.is_local:
                result = subprocess.run(
                    ["git", "-C", str(source_path), "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if line:
                            # git status --porcelain format: "XY filename" (2 status chars + space + filename)
                            filename = line[3:]
                            if " -> " in filename:
                                filename = filename.split(" -> ")[1]
                            files_to_include.append(filename)
            else:
                result = source_host.execute_command("git status --porcelain", cwd=source_path)
                if result.success:
                    for line in result.stdout.split("\n"):
                        if line:
                            # git status --porcelain format: "XY filename" (2 status chars + space + filename)
                            filename = line[3:]
                            if " -> " in filename:
                                filename = filename.split(" -> ")[1]
                            files_to_include.append(filename)

        is_include_gitignored = options.git.is_include_gitignored if options.git else False
        if is_include_gitignored:
            if source_host.is_local:
                result = subprocess.run(
                    ["git", "-C", str(source_path), "ls-files", "--others", "--ignored", "--exclude-standard"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if line:
                            files_to_include.append(line)
            else:
                result = source_host.execute_command(
                    "git ls-files --others --ignored --exclude-standard",
                    cwd=source_path,
                )
                if result.success:
                    for line in result.stdout.split("\n"):
                        if line:
                            files_to_include.append(line)

        files_to_include = list(set(files_to_include))

        if not files_to_include:
            logger.debug("No extra files to transfer")
            return

        logger.debug("Transferring extra files", count=len(files_to_include))

        # Write files to a temp file to avoid command line length limits
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            files_from_path = Path(f.name)
            for file_path in files_to_include:
                f.write(file_path + "\n")

        try:
            self._rsync_files(source_host, source_path, target_path, files_from=files_from_path, exclude_git=True)
        finally:
            files_from_path.unlink(missing_ok=True)

    def _rsync_files(
        self,
        source_host: OnlineHostInterface,
        source_path: Path,
        target_path: Path,
        extra_args: str | None = None,
        files_from: Path | None = None,
        exclude_git: bool = False,
    ) -> None:
        """Run rsync to transfer files from source to target.

        Always runs rsync from the source host, which simplifies the logic:
        - If source is local, run rsync locally (pushing to target via SSH if remote)
        - If source is remote, run rsync on source host (pushing to target via SSH if different host)
        """

        # Build rsync arguments
        rsync_args = ["rsync", "-rlpt"]
        if exclude_git:
            rsync_args.extend(["--exclude", ".git"])
        if extra_args:
            rsync_args.extend(shlex.split(extra_args))
        if files_from is not None:
            rsync_args.extend(["--files-from", str(files_from)])

        source_path_str = str(source_path).rstrip("/") + "/"
        target_path_str = str(target_path).rstrip("/") + "/"

        if source_host.is_local and self.is_local:
            # Local to local
            logger.debug("rsync: local to local")
            rsync_args.extend([source_path_str, target_path_str])
        elif source_host.is_local and not self.is_local:
            # Local to remote
            target_ssh_info = self._get_ssh_connection_info()
            assert target_ssh_info is not None
            user, hostname, port, key_path = target_ssh_info
            logger.debug("rsync: local to remote {}@{}:{}", user, hostname, port)
            rsync_args.extend(["-e", f"ssh -i {shlex.quote(str(key_path))} -p {port} -o StrictHostKeyChecking=no"])
            rsync_args.extend([source_path_str, f"{user}@{hostname}:{target_path_str}"])
        elif not source_host.is_local and self.is_local:
            # Remote to local
            source_ssh_info = source_host._get_ssh_connection_info() if isinstance(source_host, Host) else None
            assert source_ssh_info is not None
            user, hostname, port, key_path = source_ssh_info
            logger.debug("rsync: remote to local {}@{}:{}", user, hostname, port)
            rsync_args.extend(["-e", f"ssh -i {shlex.quote(str(key_path))} -p {port} -o StrictHostKeyChecking=no"])
            rsync_args.extend([f"{user}@{hostname}:{source_path_str}", target_path_str])
        else:
            # FIXME: we could implement this, but would need to support a few options:
            #  1. slow, safe: sync locally, then sync to target
            #  2. fast, safe: rsync directly between two remote hosts (requires both hosts to have SSH access to each other)
            #  3. fast, unsafe: forward SSH auth from source to target (requires SSH agent forwarding), then sync between them
            raise NotImplementedError("rsync between two remote hosts is not supported right now")

        logger.trace(" ".join(rsync_args))
        result = subprocess.run(rsync_args, capture_output=True, text=True)
        if result.returncode != 0:
            raise MngrError(f"rsync failed: {result.stderr}")

    def _create_work_dir_as_git_worktree(
        self,
        host: OnlineHostInterface,
        source_path: Path,
        options: CreateAgentOptions,
    ) -> Path:
        """Create a work_dir using git worktree."""
        if host.id != self.id:
            raise UserInputError("Worktree mode only works when source is on the same host")

        agent_id = AgentId.generate()
        work_dir_path = options.target_path
        if work_dir_path is None:
            work_dir_path = self.host_dir / "worktrees" / str(agent_id)

        self._mkdir(work_dir_path.parent)

        branch_name = self._determine_branch_name(options)

        logger.debug("Creating git worktree", path=str(work_dir_path), branch=branch_name)
        cmd = f"git -C {shlex.quote(str(source_path))} worktree add {shlex.quote(str(work_dir_path))} -b {shlex.quote(branch_name)}"

        if options.git and options.git.base_branch:
            cmd += f" {shlex.quote(options.git.base_branch)}"

        result = self.execute_command(cmd)
        if not result.success:
            raise MngrError(f"Failed to create git worktree: {result.stderr}")

        # Track generated work directories at the host level
        self._add_generated_work_dir(work_dir_path)

        return work_dir_path

    def _determine_branch_name(self, options: CreateAgentOptions) -> str:
        """Determine the branch name for a new work_dir."""
        if options.git and options.git.new_branch_name:
            return options.git.new_branch_name

        agent_name = options.name or AgentName("agent")
        provider_name = self.provider_instance.name
        branch_prefix = options.git.new_branch_prefix if options.git else "mngr/"

        return f"{branch_prefix}{agent_name}-{provider_name}"

    def create_agent_state(
        self,
        work_dir_path: Path,
        options: CreateAgentOptions,
    ) -> AgentInterface:
        """Create the agent state directory and return the agent."""
        agent_id = AgentId.generate()
        agent_name = options.name or AgentName(f"agent-{str(agent_id)}")
        agent_type = options.agent_type or AgentTypeName("claude")
        logger.debug(
            "Creating agent state",
            agent_id=str(agent_id),
            agent_name=str(agent_name),
            agent_type=str(agent_type),
        )

        resolved = resolve_agent_type(agent_type, self.mngr_ctx.config)

        state_dir = self.host_dir / "agents" / str(agent_id)
        self._mkdirs([state_dir, state_dir / "logs", state_dir / "events"])

        create_time = datetime.now(timezone.utc)

        agent = cast(type[BaseAgent], resolved.agent_class)(
            id=agent_id,
            name=agent_name,
            agent_type=agent_type,
            work_dir=work_dir_path,
            create_time=create_time,
            host_id=self.id,
            host=self,
            mngr_ctx=self.mngr_ctx,
            agent_config=resolved.agent_config,
        )

        command = agent.assemble_command(
            host=self,
            agent_args=options.agent_args,
            command_override=options.command,
        )
        command_str = str(command)

        data = {
            "id": str(agent_id),
            "name": str(agent_name),
            "type": str(agent_type),
            "work_dir": str(work_dir_path),
            "create_time": create_time.isoformat(),
            "command": command_str,
            "additional_commands": [
                {"command": str(cmd.command), "window_name": cmd.window_name} for cmd in options.additional_commands
            ],
            "initial_message": options.initial_message,
            "resume_message": options.resume_message,
            "message_delay_seconds": options.message_delay_seconds,
            "permissions": [],
            "start_on_boot": False,
        }

        data_path = state_dir / "data.json"
        self.write_text_file(data_path, json.dumps(data, indent=2))

        # Persist agent data to external storage (e.g., Modal volume)
        self.provider_instance.persist_agent_data(self.id, data)

        # Record CREATE activity for idle detection
        agent.record_activity(ActivitySource.CREATE)

        return agent

    def _get_agent_state_dir(self, agent: AgentInterface) -> Path:
        """Get the state directory for an agent."""
        return self.host_dir / "agents" / str(agent.id)

    def _get_agent_env_path(self, agent: AgentInterface) -> Path:
        """Get the path to the agent's environment file."""
        return self._get_agent_state_dir(agent) / "env"

    def _collect_agent_env_vars(
        self,
        agent: AgentInterface,
        options: CreateAgentOptions,
    ) -> dict[str, str]:
        """Collect environment variables from options.

        Combines env vars from:
        1. MNGR-specific agent variables (id, name, state_dir, work_dir)
        2. programmatic defaults
        3. env_files (loaded in order)
        4. env_vars (explicit KEY=VALUE pairs)

        Later sources override earlier ones.

        Note: pass_env_vars is resolved at the CLI level before this is called,
        and merged into env_vars with explicit env_vars taking precedence.
        """
        env_vars: dict[str, str] = {}

        # 1. Add MNGR-specific environment variables
        agent_state_dir = self._get_agent_state_dir(agent)
        env_vars["MNGR_HOST_DIR"] = str(self.host_dir)
        env_vars["MNGR_AGENT_ID"] = str(agent.id)
        env_vars["MNGR_AGENT_NAME"] = str(agent.name)
        env_vars["MNGR_AGENT_STATE_DIR"] = str(agent_state_dir)
        env_vars["MNGR_AGENT_WORK_DIR"] = str(agent.work_dir)

        # 2. Add programmatic defaults
        env_vars["GIT_BASE_BRANCH"] = (options.git.base_branch if options.git else None) or ""

        # 3. Load from env_files
        for env_file in options.environment.env_files:
            content = env_file.read_text()
            file_vars = parse_env_file(content)
            env_vars.update(file_vars)

        # 4. Add explicit env_vars
        for env_var in options.environment.env_vars:
            env_vars[env_var.key] = env_var.value

        return env_vars

    def _write_agent_env_file(self, agent: AgentInterface, env_vars: Mapping[str, str]) -> None:
        """Write environment variables to the agent's env file."""
        if not env_vars:
            return

        env_path = self._get_agent_env_path(agent)
        content = _format_env_file(env_vars)
        self.write_text_file(env_path, content)
        logger.debug("Wrote env vars", count=len(env_vars), path=str(env_path))

    def _build_source_env_commands(self, agent: AgentInterface) -> list[str]:
        """Build shell commands that source host and agent env files.

        Returns a list of shell commands that:
        1. Set 'set -a' to auto-export all sourced variables
        2. Source host env if it exists (host env first)
        3. Source agent env if it exists (agent can override host)
        4. Restore with 'set +a'

        The caller is responsible for joining these appropriately.
        """
        host_env_path = self.host_dir / "env"
        agent_env_path = self._get_agent_env_path(agent)

        return [
            "set -a",
            f"[ -f {shlex.quote(str(host_env_path))} ] && . {shlex.quote(str(host_env_path))} || true",
            f"[ -f {shlex.quote(str(agent_env_path))} ] && . {shlex.quote(str(agent_env_path))} || true",
            "set +a",
        ]

    def _build_source_env_prefix(self, agent: AgentInterface) -> str:
        """Build a shell prefix that sources host and agent env files if they exist."""
        commands = self._build_source_env_commands(agent)
        return " && ".join(commands) + " && "

    def provision_agent(
        self,
        agent: AgentInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Provision an agent (install packages, configure, etc.).

        Applies all provisioning in a logical order:
        1. Call agent.on_before_provisioning() (validation only)
        2. Call agent.get_provision_file_transfers() to collect file transfers
        3. Validate required files exist, execute file transfers
        4. Call agent.provision() (agent-type-specific provisioning)
        5. Create directories (so paths exist for uploads)
        6. Upload files (files exist before modifications)
        7. Append text to files
        8. Prepend text to files
        9. Write environment variables to agent env file
        10. Run sudo commands (system-level setup, with env vars sourced)
        11. Run user commands (user-level setup, with env vars sourced)
        12. Call agent.on_after_provisioning() (finalization)
        """
        # 1. Call pre-provisioning validation on agent
        logger.debug("Calling on_before_provisioning for agent {}", agent.name)
        agent.on_before_provisioning(host=self, options=options, mngr_ctx=mngr_ctx)

        # 2. Collect file transfers from agent
        logger.debug("Collecting file transfers for agent {}", agent.name)
        all_file_transfers = list(agent.get_provision_file_transfers(host=self, options=options, mngr_ctx=mngr_ctx))

        # 3. Validate required files exist and execute transfers
        self._execute_agent_file_transfers(agent, all_file_transfers)

        # 4. Call agent.provision() for agent-type-specific provisioning
        logger.debug("Calling provision for agent {}", agent.name)
        agent.provision(host=self, options=options, mngr_ctx=mngr_ctx)

        provisioning = options.provisioning
        logger.debug(
            "Applying user provisioning commands",
            agent_name=str(agent.name),
            dirs=len(provisioning.create_directories),
            uploads=len(provisioning.upload_files),
            appends=len(provisioning.append_to_files),
            prepends=len(provisioning.prepend_to_files),
            sudo_cmds=len(provisioning.sudo_commands),
            user_cmds=len(provisioning.user_commands),
        )

        # 5. Create directories
        for directory in provisioning.create_directories:
            logger.trace("Creating directory: {}", directory)
            self._mkdir(directory)

        # 6. Upload files (read from local filesystem, write to host)
        for upload_spec in provisioning.upload_files:
            logger.trace("Uploading file: {} -> {}", upload_spec.local_path, upload_spec.remote_path)
            # Read from local filesystem (not via host primitives)
            local_content = upload_spec.local_path.read_bytes()
            self.write_file(upload_spec.remote_path, local_content)

        # 7. Append text to files
        for append_spec in provisioning.append_to_files:
            logger.trace("Appending to file: {}", append_spec.remote_path)
            self._append_to_file(append_spec.remote_path, append_spec.text)

        # 8. Prepend text to files
        for prepend_spec in provisioning.prepend_to_files:
            logger.trace("Prepending to file: {}", prepend_spec.remote_path)
            self._prepend_to_file(prepend_spec.remote_path, prepend_spec.text)

        # 9. Write environment variables to agent env file
        env_vars = self._collect_agent_env_vars(agent, options)
        self._write_agent_env_file(agent, env_vars)

        # Build the source prefix for commands (sources host env, then agent env)
        source_prefix = self._build_source_env_prefix(agent)

        # 10. Run sudo commands (with env vars sourced)
        for cmd in provisioning.sudo_commands:
            logger.trace("Running sudo command: {}", cmd)
            result = self._run_sudo_command(source_prefix + cmd)
            if not result.success:
                raise MngrError(f"Sudo command failed: {cmd}\nstderr: {result.stderr}")

        # 11. Run user commands (with env vars sourced)
        for cmd in provisioning.user_commands:
            logger.trace("Running user command: {}", cmd)
            result = self.execute_command(source_prefix + cmd, cwd=agent.work_dir)
            if not result.success:
                raise MngrError(f"User command failed: {cmd}\nstderr: {result.stderr}")

        # 12. Call post-provisioning on agent
        logger.debug("Calling on_after_provisioning for agent {}", agent.name)
        agent.on_after_provisioning(host=self, options=options, mngr_ctx=mngr_ctx)

    def _execute_agent_file_transfers(
        self,
        agent: AgentInterface,
        transfers: list[FileTransferSpec],
    ) -> None:
        """Validate and execute file transfers from the agent.

        First validates that all required files exist, then executes transfers.
        """
        if not transfers:
            return

        # Validate required files first
        missing_required: list[Path] = []
        for transfer in transfers:
            if transfer.is_required and not transfer.local_path.exists():
                missing_required.append(transfer.local_path)

        if missing_required:
            missing_str = ", ".join(str(p) for p in missing_required)
            raise MngrError(f"Required files for provisioning not found: {missing_str}")

        # Execute transfers
        for transfer in transfers:
            if not transfer.local_path.exists():
                # Optional file doesn't exist, skip it
                logger.trace("Skipping optional file transfer (file not found): {}", transfer.local_path)
                continue

            # Resolve relative remote paths to work_dir
            remote_path = agent.work_dir / transfer.agent_path

            logger.trace("Agent file transfer: {} -> {}", transfer.local_path, remote_path)
            local_content = transfer.local_path.read_bytes()
            self.write_file(remote_path, local_content)

    def _append_to_file(self, path: Path, text: str) -> None:
        """Append text to a file, creating it if it doesn't exist."""
        try:
            existing_content = self.read_text_file(path)
        except FileNotFoundError:
            existing_content = ""
        self.write_text_file(path, existing_content + text)

    def _prepend_to_file(self, path: Path, text: str) -> None:
        """Prepend text to a file, creating it if it doesn't exist."""
        try:
            existing_content = self.read_text_file(path)
        except FileNotFoundError:
            existing_content = ""
        self.write_text_file(path, text + existing_content)

    def _run_sudo_command(self, command: str) -> CommandResult:
        """Run a command with sudo privileges."""
        success, output = self._run_shell_command(
            StringCommand(command),
            _sudo=True,
        )
        return CommandResult(
            stdout=output.stdout,
            stderr=output.stderr,
            success=success,
        )

    def destroy_agent(self, agent: AgentInterface) -> None:
        """Destroy an agent and clean up its resources."""
        logger.debug("Destroying agent", agent_id=str(agent.id), agent_name=str(agent.name))
        self.stop_agents([agent.id])
        state_dir = self.host_dir / "agents" / str(agent.id)
        self._remove_directory(state_dir)

        # Remove persisted agent data from external storage (e.g., Modal volume)
        self.provider_instance.remove_persisted_agent_data(self.id, agent.id)

    def _build_env_shell_command(self, agent: AgentInterface) -> str:
        """Build a shell command that sources env files and then execs bash.

        This is used as the shell-command for tmux new-session/new-window, so the
        resulting shell has all environment variables properly set.
        """
        commands = self._build_source_env_commands(agent)
        commands.append("exec bash")
        return "bash -c " + shlex.quote("; ".join(commands))

    def _get_host_tmux_config_path(self) -> Path:
        """Get the path to the host's tmux config file.

        Using a host-level config instead of per-agent configs avoids issues
        where tmux key bindings (which are server-wide) would be overwritten
        by each new agent, causing Ctrl-q to destroy the wrong agent.
        """
        return self.host_dir / "tmux.conf"

    def _create_host_tmux_config(self) -> Path:
        """Create a tmux config file for the host with hotkeys for agent management.

        The config:
        1. Sources the user's default tmux config if it exists (~/.tmux.conf)
        2. Adds a Ctrl-q binding that detaches and destroys the current agent
        3. Adds a Ctrl-s binding that detaches and stops the current agent

        This uses the tmux session_name format variable in the commands,
        which expands to the current session name at runtime. This approach
        works correctly even when multiple agents share a tmux server, because
        each session's binding correctly references its own session name.

        Returns the path to the created config file.
        """
        config_path = self._get_host_tmux_config_path()

        # Build the config content
        # The session_name variable is a tmux format that gets expanded at runtime
        # Yes, it has to get passed through in this weird way
        lines = [
            "# Mngr host tmux config",
            "# Auto-generated - do not edit",
            "",
            "# Source user's default tmux config if it exists",
            "if-shell 'test -f ~/.tmux.conf' 'source-file ~/.tmux.conf'",
            "",
            "# Ctrl-q: Detach and destroy the agent whose session this is",
            """bind -n C-q run-shell 'SESSION=$(tmux display-message -p "#{session_name}"); tmux detach-client -E "mngr destroy --session $SESSION -f"'""",
            "",
            "# Ctrl-t: Detach and stop the agent whose session this is",
            """bind -n C-t run-shell 'SESSION=$(tmux display-message -p "#{session_name}"); tmux detach-client -E "mngr stop --session $SESSION"'""",
            "",
            # FIXME: this should really be handled by the agent plugin instead! It will need to append to the tmux conf as part of its setup (if this line doesnt already exist, then remove it from here)
            "# Automatically signal claude to tell it to resize on client attach",
            """set-hook -g client-attached 'run-shell "pkill -SIGWINCH -f claude"'""",
            "",
        ]
        config_content = "\n".join(lines)

        self.write_text_file(config_path, config_content)
        logger.debug("Created host tmux config at {}", config_path)

        return config_path

    def start_agents(self, agent_ids: Sequence[AgentId]) -> None:
        """Start agents by creating their tmux sessions.

        Creates a tmux session and uses send-keys to type and execute the command.
        This allows the user to hit ctrl-c and then up arrow to see and restart
        the command.

        If additional_commands are configured, creates new tmux windows in the
        same session for each additional command.

        Environment variables from the host and agent env files are sourced
        when creating the tmux session, so all shells in the session inherit them.

        A custom tmux config is used that:
        - Sources the user's default ~/.tmux.conf if it exists
        - Adds a Ctrl-q binding to detach and destroy the current agent
        - Adds a Ctrl-t binding to detach and halt (stop) the current agent
        """
        logger.debug("Starting {} agent(s)", len(agent_ids))

        # Create the host-level tmux config (shared by all agents on this host)
        # This avoids the issue where per-agent configs would overwrite each other's
        # Ctrl-q bindings since tmux key bindings are server-wide
        tmux_config_path = self._create_host_tmux_config()

        for agent_id in agent_ids:
            agent = self._get_agent_by_id(agent_id)
            if agent is None:
                raise AgentNotFoundOnHostError(agent_id, self.id)

            command = self._get_agent_command(agent)
            additional_commands = self._get_agent_additional_commands(agent)

            session_name = f"{self.mngr_ctx.config.prefix}{agent.name}"
            logger.debug("Starting agent {} in tmux session {}", agent.name, session_name)

            # Build a shell command that sources env files and execs bash
            # This ensures the tmux session's shell has the env vars set
            env_shell_cmd = self._build_env_shell_command(agent)

            # Build unset environment variable arguments
            unset_env_args = ""
            for var_name in self.mngr_ctx.config.unset_vars:
                unset_env_args += f"unset {shlex.quote(var_name)} && "

            # Create a tmux session with a shell that has env vars sourced
            # The shell-command argument makes tmux start with our custom bash
            # that sources the env files before becoming an interactive shell
            # The -f flag specifies our custom tmux config with the exit hotkey binding
            # Note: env_shell_cmd must be quoted so it's passed as a single argument to tmux
            # The -d flag creates a detached session; tmux returns after the session is created
            result = self.execute_command(
                f"{unset_env_args}tmux -f {shlex.quote(str(tmux_config_path))} new-session -d -s '{session_name}' -c '{agent.work_dir}' {shlex.quote(env_shell_cmd)}"
            )
            if not result.success:
                raise AgentStartError(str(agent.name), f"tmux new-session failed: {result.stderr}")

            # Set the session's default-command so any new window/pane created
            # by the user will automatically source the env files
            # Note: env_shell_cmd needs to be quoted as a single argument for tmux
            result = self.execute_command(
                f"tmux set-option -t '{session_name}' default-command {shlex.quote(env_shell_cmd)}"
            )
            if not result.success:
                raise AgentStartError(str(agent.name), f"tmux set-option failed: {result.stderr}")

            # Send the command as literal keys (tmux will handle escaping)
            # Using -l flag to send literal characters
            result = self.execute_command(f"tmux send-keys -t '{session_name}' -l {shlex.quote(command)}")
            if not result.success:
                raise AgentStartError(str(agent.name), f"tmux send-keys failed: {result.stderr}")

            # Send Enter to execute the command
            result = self.execute_command(f"tmux send-keys -t '{session_name}' Enter")
            if not result.success:
                raise AgentStartError(str(agent.name), f"tmux send-keys Enter failed: {result.stderr}")

            # Create additional windows for each additional command
            for idx, named_cmd in enumerate(additional_commands):
                window_name = named_cmd.window_name if named_cmd.window_name else f"cmd-{idx + 1}"
                logger.debug(
                    "Creating additional tmux window {} for command: {}",
                    window_name,
                    named_cmd.command,
                )

                # Create a new window with a shell that has env vars sourced
                # Note: env_shell_cmd must be quoted so it's passed as a single argument to tmux
                result = self.execute_command(
                    f"tmux new-window -t '{session_name}' -n '{window_name}' -c '{agent.work_dir}' {shlex.quote(env_shell_cmd)}"
                )
                if not result.success:
                    raise AgentStartError(
                        str(agent.name), f"tmux new-window failed for {window_name}: {result.stderr}"
                    )

                # Send the additional command as literal keys
                result = self.execute_command(
                    f"tmux send-keys -t '{session_name}:{window_name}' -l {shlex.quote(str(named_cmd.command))}"
                )
                if not result.success:
                    raise AgentStartError(str(agent.name), f"tmux send-keys failed for {window_name}: {result.stderr}")

                # Send Enter to execute the command
                result = self.execute_command(f"tmux send-keys -t '{session_name}:{window_name}' Enter")
                if not result.success:
                    raise AgentStartError(
                        str(agent.name), f"tmux send-keys Enter failed for {window_name}: {result.stderr}"
                    )

            # If we created additional windows, select the first window (the main agent)
            if additional_commands:
                result = self.execute_command(f"tmux select-window -t '{session_name}:0'")
                if not result.success:
                    raise AgentStartError(str(agent.name), f"tmux select-window failed: {result.stderr}")

            # Record START activity for idle detection
            agent.record_activity(ActivitySource.START)

            # Start background process activity monitor
            self._start_process_activity_monitor(agent, session_name)

    def _start_process_activity_monitor(self, agent: AgentInterface, session_name: str) -> None:
        """Start a background process that writes PROCESS activity while the agent is alive.

        This launches a detached bash script on the host that:
        1. Gets the tmux pane PID for the agent's session
        2. Loops while that PID is alive, writing PROCESS activity every ~5 seconds
        3. Exits when the pane process exits

        The activity file contains JSON with:
        - time: milliseconds since Unix epoch (int)
        - pane_pid: the tmux pane PID being monitored (for debugging)
        - agent_id: the agent's ID (for debugging)

        Note: The authoritative activity time is the file's mtime, not the JSON content.
        """
        activity_path = self.host_dir / "agents" / str(agent.id) / "activity" / ActivitySource.PROCESS.value.lower()
        agent_id = str(agent.id)

        # Build a bash script that monitors the process and writes activity
        # We use nohup and redirect output to /dev/null to fully detach
        # The script:
        # 1. Gets the pane PID using tmux list-panes
        # 2. While the PID exists, write activity JSON and sleep
        # 3. Uses date +%s for seconds since epoch, multiply by 1000 for milliseconds
        # FIXME: this script really ought to wait for up to X seconds for the PANE_PID to appear (since it can take a little bit)
        monitor_script = f"""
PANE_PID=$(tmux list-panes -t {shlex.quote(session_name)} -F '#{{pane_pid}}' 2>/dev/null | head -n 1)
if [ -z "$PANE_PID" ]; then
    exit 0
fi
ACTIVITY_PATH={shlex.quote(str(activity_path))}
AGENT_ID={shlex.quote(agent_id)}
mkdir -p "$(dirname "$ACTIVITY_PATH")"
while kill -0 "$PANE_PID" 2>/dev/null; do
    TIME_MS=$(($(date +%s) * 1000))
    printf '{{\\n  "time": %d,\\n  "pane_pid": %s,\\n  "agent_id": "%s"\\n}}\\n' "$TIME_MS" "$PANE_PID" "$AGENT_ID" > "$ACTIVITY_PATH"
    sleep 5
done
"""
        # Run the script in the background, fully detached
        # nohup ensures it survives if the parent shell exits
        # Redirect all output to /dev/null and background with &
        cmd = f"nohup bash -c {shlex.quote(monitor_script)} </dev/null >/dev/null 2>&1 &"

        result = self.execute_command(cmd)
        if not result.success:
            logger.warning(
                "Failed to start process activity monitor for agent {}: {}",
                agent.name,
                result.stderr,
            )

    def _get_all_descendant_pids(self, parent_pid: str) -> list[str]:
        """Recursively get all descendant PIDs of a given parent PID."""
        descendant_pids: list[str] = []

        # Get immediate children
        result = self.execute_command(f"pgrep -P {parent_pid} 2>/dev/null || true")
        if result.success and result.stdout.strip():
            child_pids = result.stdout.strip().split("\n")
            for child_pid in child_pids:
                if child_pid:
                    descendant_pids.append(child_pid)
                    # Recursively get descendants of this child
                    descendant_pids.extend(self._get_all_descendant_pids(child_pid))

        return descendant_pids

    def _collect_session_pids(self, session_name: str) -> list[str]:
        """Collect all pane PIDs and their descendants for a tmux session.

        Uses -s flag to list panes across ALL windows in the session, not just the
        current window. This is important for sessions with additional command windows.
        """
        all_pids: list[str] = []
        result = self.execute_command(
            f"tmux list-panes -s -t '{session_name}' -F '#{{pane_pid}}' 2>/dev/null || true"
        )
        if result.success and result.stdout.strip():
            for pane_pid in result.stdout.strip().split("\n"):
                if pane_pid:
                    all_pids.append(pane_pid)
                    all_pids.extend(self._get_all_descendant_pids(pane_pid))
        return all_pids

    def stop_agents(self, agent_ids: Sequence[AgentId], timeout_seconds: float = 5.0) -> None:
        """Stop agents by killing all processes in their tmux sessions.

        This ensures all processes in all panes are terminated by:
        1. Getting all PIDs (panes + descendants)
        2. Sending SIGTERM to each individual process
        3. Waiting briefly, then sending SIGKILL to any survivors
        4. Finally killing the tmux session itself
        """
        logger.debug("Stopping {} agent(s) with timeout={}s", len(agent_ids), timeout_seconds)
        all_pids: list[str] = []

        current_agents: list[AgentInterface] = []

        for agent_id in agent_ids:
            agent = self._get_agent_by_id(agent_id)
            if agent is None:
                continue

            current_agents.append(agent)
            session_name = f"{self.mngr_ctx.config.prefix}{agent.name}"
            all_pids.extend(self._collect_session_pids(session_name))

        if all_pids:
            pid_list = " ".join(all_pids)

            # Send SIGTERM to all processes at once, then wait briefly and SIGKILL survivors.
            # This is done in a single shell command to avoid the issue where one non-responsive
            # process (e.g., interactive bash which ignores SIGTERM) would consume the entire
            # timeout budget in a serial loop, preventing SIGKILL from reaching other processes.
            grace_seconds = min(1.0, timeout_seconds)
            self.execute_command(
                f"for p in {pid_list}; do kill -TERM $p 2>/dev/null; done; "
                f"sleep {grace_seconds}; "
                f"for p in {pid_list}; do kill -KILL $p 2>/dev/null; done; true"
            )

        # Finally kill the tmux sessions themselves
        for agent in current_agents:
            session_name = f"{self.mngr_ctx.config.prefix}{agent.name}"
            self.execute_command(f"tmux kill-session -t '{session_name}' 2>/dev/null || true")

    def _get_agent_by_id(self, agent_id: AgentId) -> AgentInterface | None:
        """Get an agent by ID."""
        agents = self.get_agents()
        for agent in agents:
            if agent.id == agent_id:
                return agent
        return None

    def _get_agent_command(self, agent: AgentInterface) -> str:
        """Get the command for an agent."""
        data_path = self.host_dir / "agents" / str(agent.id) / "data.json"
        try:
            content = self.read_text_file(data_path)
        except FileNotFoundError as e:
            raise NoCommandDefinedError(f"No data.json file for agent {agent.name} ({agent.id})") from e

        data = json.loads(content)
        try:
            return data["command"]
        except KeyError as e:
            raise NoCommandDefinedError(f"No command in data.json for agent {agent.name} ({agent.id})") from e

    def _get_agent_additional_commands(self, agent: AgentInterface) -> list[NamedCommand]:
        """Get the additional commands for an agent."""
        data_path = self.host_dir / "agents" / str(agent.id) / "data.json"
        try:
            content = self.read_text_file(data_path)
        except FileNotFoundError:
            return []

        data = json.loads(content)
        raw_commands = data.get("additional_commands", [])

        # Handle both old format (list of strings) and new format (list of dicts)
        result: list[NamedCommand] = []
        for cmd in raw_commands:
            if isinstance(cmd, str):
                # Old format: plain string
                result.append(NamedCommand(command=cmd, window_name=None))
            else:
                # New format: dict with command and window_name
                result.append(NamedCommand(command=cmd["command"], window_name=cmd.get("window_name")))
        return result

    # =========================================================================
    # Agent-Derived Information
    # =========================================================================

    def get_idle_seconds(self) -> float:
        """Get the number of seconds since last activity.

        Checks both host-level activity files (like BOOT) and agent-level
        activity files (like CREATE, START, AGENT). Returns the time since
        the most recent activity from any source.
        """
        latest_activity: datetime | None = None

        # Check host-level activity files
        for activity_type in ActivitySource:
            activity_time = self.get_reported_activity_time(activity_type)
            if activity_time is not None:
                if latest_activity is None or activity_time > latest_activity:
                    latest_activity = activity_time

        # Check agent-level activity files for all agents on this host
        for agent in self.get_agents():
            for activity_type in ActivitySource:
                activity_time = agent.get_reported_activity_time(activity_type)
                if activity_time is not None:
                    if latest_activity is None or activity_time > latest_activity:
                        latest_activity = activity_time

        if latest_activity is None:
            return float("inf")

        now = datetime.now(timezone.utc)
        return (now - latest_activity).total_seconds()

    def get_state(self) -> HostState:
        """Get the current state of the host."""
        logger.trace("Getting state for host {}", self.id)
        if self.is_local:
            logger.trace("Host {} is local, state=RUNNING", self.id)
            return HostState.RUNNING

        try:
            result = self.execute_command("echo ok")
            if result.success:
                logger.trace("Host {} state=RUNNING (ping successful)", self.id)
                return HostState.RUNNING
        except (OSError, HostConnectionError):
            pass

        # otherwise use the offline logic
        return super().get_state()


@pure
def _format_env_file(env: Mapping[str, str]) -> str:
    """Format a dict as an environment file."""
    lines: list[str] = []
    for key, value in env.items():
        if " " in value or '"' in value or "'" in value or "\n" in value:
            value = '"' + value.replace('"', '\\"') + '"'
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"
