# Testing implementation of ModalInterface that fakes Modal locally.
#
# Volumes are backed by real directories on disk. Sandboxes run commands
# locally via subprocess. Images are lightweight no-ops. Apps and
# environments are thin metadata.

import os
import shutil
import signal
import subprocess
import time
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Mapping
from typing import Sequence

from pydantic import ConfigDict
from pydantic import Field
from pydantic import PrivateAttr

from imbue.modal_proxy.data_types import FileEntry
from imbue.modal_proxy.data_types import FileEntryType
from imbue.modal_proxy.data_types import StreamType
from imbue.modal_proxy.data_types import TunnelInfo
from imbue.modal_proxy.errors import ModalProxyError
from imbue.modal_proxy.errors import ModalProxyNotFoundError
from imbue.modal_proxy.interface import AppInterface
from imbue.modal_proxy.interface import ExecOutput
from imbue.modal_proxy.interface import ExecProcess
from imbue.modal_proxy.interface import FunctionInterface
from imbue.modal_proxy.interface import ImageInterface
from imbue.modal_proxy.interface import ModalInterface
from imbue.modal_proxy.interface import SandboxInterface
from imbue.modal_proxy.interface import SecretInterface
from imbue.modal_proxy.interface import VolumeInterface

# ---------------------------------------------------------------------------
# Object implementations
# ---------------------------------------------------------------------------


class TestingExecOutput(ExecOutput):
    """Exec output backed by a completed subprocess result."""

    output_text: str = Field(default="", description="The captured stdout text")

    def read(self) -> str:
        return self.output_text


class TestingExecProcess(ExecProcess):
    """Exec process backed by a local subprocess."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _completed_text: str = PrivateAttr(default="")
    _process: subprocess.Popen[str] | None = PrivateAttr(default=None)

    def get_stdout(self) -> ExecOutput:
        if self._process is not None:
            # Background process -- read what's available
            stdout_text = ""
            if self._process.stdout is not None:
                stdout_text = self._process.stdout.read() or ""
            return TestingExecOutput(output_text=stdout_text)
        return TestingExecOutput(output_text=self._completed_text)

    def wait(self) -> None:
        if self._process is not None:
            self._process.wait()


class TestingSecret(SecretInterface):
    """In-memory secret holding key-value pairs."""

    values: dict[str, str | None] = Field(default_factory=dict, description="Secret key-value pairs")


class TestingFunction(FunctionInterface):
    """Testing function with a configurable web URL."""

    url: str | None = Field(default=None, description="The web URL for this function")

    def get_web_url(self) -> str | None:
        return self.url


class TestingImage(ImageInterface):
    """Lightweight no-op image for testing."""

    image_id: str = Field(description="Unique identifier for this image")

    def get_object_id(self) -> str:
        return self.image_id

    def apt_install(self, *packages: str) -> "ImageInterface":
        # No-op -- packages are already installed in the test environment
        return TestingImage(image_id=self.image_id)

    def dockerfile_commands(
        self,
        commands: Sequence[str],
        *,
        context_dir: Path | None = None,
        secrets: Sequence[SecretInterface] = (),
    ) -> "ImageInterface":
        # No-op -- return a new image with a fresh ID to simulate layer caching
        return TestingImage(image_id=f"img-{uuid.uuid4().hex[:12]}")


class TestingVolume(VolumeInterface):
    """Volume backed by a real directory on disk."""

    root_dir: Path = Field(description="Local directory backing this volume")
    volume_name: str | None = Field(default=None, description="Volume name if known")

    def get_name(self) -> str | None:
        return self.volume_name

    def _resolve(self, path: str) -> Path:
        """Resolve a volume path to a local filesystem path."""
        # Strip leading slash and resolve relative to root
        clean = path.lstrip("/")
        resolved = (self.root_dir / clean).resolve()
        # Ensure we don't escape the root directory
        if not str(resolved).startswith(str(self.root_dir.resolve())):
            raise ModalProxyError(f"Path escapes volume root: {path}")
        return resolved

    def listdir(self, path: str) -> list[FileEntry]:
        target = self._resolve(path)
        if not target.exists():
            raise ModalProxyNotFoundError(f"Path not found: {path}")
        if not target.is_dir():
            raise ModalProxyError(f"Not a directory: {path}")
        entries: list[FileEntry] = []
        for child in sorted(target.iterdir()):
            relative = str(child.relative_to(self.root_dir))
            stat = child.stat()
            entries.append(
                FileEntry(
                    path=relative,
                    type=FileEntryType.DIRECTORY if child.is_dir() else FileEntryType.FILE,
                    mtime=stat.st_mtime,
                    size=stat.st_size if child.is_file() else 0,
                )
            )
        return entries

    def read_file(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.exists():
            raise ModalProxyNotFoundError(f"File not found: {path}")
        if not target.is_file():
            raise ModalProxyError(f"Not a file: {path}")
        return target.read_bytes()

    def remove_file(self, path: str, *, recursive: bool = False) -> None:
        target = self._resolve(path)
        if not target.exists():
            raise ModalProxyNotFoundError(f"Path not found: {path}")
        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                raise ModalProxyError(f"Cannot remove directory without recursive=True: {path}")
        else:
            target.unlink()

    def write_files(self, file_contents_by_path: Mapping[str, bytes]) -> None:
        for path, data in file_contents_by_path.items():
            target = self._resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def reload(self) -> None:
        # No-op -- local filesystem is always up to date
        pass

    def commit(self) -> None:
        # No-op -- writes are immediate on local filesystem
        pass


class TestingSandbox(SandboxInterface):
    """Sandbox that runs commands locally via subprocess.

    Processes launched via exec are tracked so they can be cleaned up
    when the sandbox is terminated.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    sandbox_id: str = Field(description="Unique identifier for this sandbox")
    _tags: dict[str, str] = PrivateAttr(default_factory=dict)
    _is_terminated: bool = PrivateAttr(default=False)
    _background_processes: list[subprocess.Popen[str]] = PrivateAttr(default_factory=list)
    _snapshot_count: int = PrivateAttr(default=0)

    def get_object_id(self) -> str:
        return self.sandbox_id

    def exec(
        self,
        *args: str,
        stdout: StreamType = StreamType.PIPE,
        stderr: StreamType = StreamType.PIPE,
    ) -> ExecProcess:
        if self._is_terminated:
            raise ModalProxyError("Sandbox has been terminated")

        stdout_pipe = subprocess.PIPE if stdout == StreamType.PIPE else subprocess.DEVNULL
        stderr_pipe = subprocess.PIPE if stderr == StreamType.PIPE else subprocess.DEVNULL

        # Check if this is a "background" command (like sshd -D or nohup)
        # that should not block
        is_background = False
        if args and (
            args[-1] == "&"
            or (len(args) >= 2 and args[0] == "/usr/sbin/sshd" and "-D" in args)
            or (len(args) >= 2 and "nohup" in args[0])
        ):
            is_background = True

        if is_background:
            process = subprocess.Popen(
                args,
                stdout=stdout_pipe,
                stderr=stderr_pipe,
                text=True,
            )
            self._background_processes.append(process)
            exec_proc = TestingExecProcess()
            exec_proc._process = process
            return exec_proc
        else:
            result = subprocess.run(
                args,
                stdout=stdout_pipe,
                stderr=stderr_pipe,
                text=True,
                timeout=60,
            )
            exec_proc = TestingExecProcess()
            exec_proc._completed_text = result.stdout or ""
            return exec_proc

    def tunnels(self) -> dict[int, TunnelInfo]:
        if self._is_terminated:
            raise ModalProxyError("Sandbox has been terminated")
        # Return a fixed tunnel for SSH port 22 -> localhost:22222
        # Tests should set up their own SSH server if needed
        return {22: TunnelInfo(tcp_socket=("127.0.0.1", 22222))}

    def get_tags(self) -> dict[str, str]:
        return dict(self._tags)

    def set_tags(self, tags: Mapping[str, str]) -> None:
        self._tags = dict(tags)

    def snapshot_filesystem(self, timeout: int = 120) -> ImageInterface:
        if self._is_terminated:
            raise ModalProxyError("Sandbox has been terminated")
        self._snapshot_count += 1
        image_id = f"snap-{self.sandbox_id}-{self._snapshot_count}"
        return TestingImage(image_id=image_id)

    def terminate(self) -> None:
        if self._is_terminated:
            return
        self._is_terminated = True
        # Kill all tracked background processes
        for process in self._background_processes:
            try:
                os.kill(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
        self._background_processes.clear()


class TestingApp(AppInterface):
    """Lightweight testing app with a generated ID."""

    app_id: str = Field(description="Unique app identifier")
    app_name: str = Field(description="Human-readable app name")

    def get_app_id(self) -> str:
        return self.app_id

    def get_name(self) -> str:
        return self.app_name

    def run(self, *, environment_name: str) -> Generator["AppInterface", None, None]:
        yield self


# ---------------------------------------------------------------------------
# Top-level implementation
# ---------------------------------------------------------------------------


class TestingModalInterface(ModalInterface):
    """Testing implementation of ModalInterface that fakes Modal locally.

    All state is held in memory and on the local filesystem (for volumes).
    No network calls are made. This implementation is designed for testing
    mng_modal without requiring Modal credentials or a Modal account.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    root_dir: Path = Field(description="Root directory for volume storage")
    _environments: set[str] = PrivateAttr(default_factory=set)
    _apps: dict[str, TestingApp] = PrivateAttr(default_factory=dict)
    _volumes: dict[str, TestingVolume] = PrivateAttr(default_factory=dict)
    _sandboxes: list[TestingSandbox] = PrivateAttr(default_factory=list)
    _functions: dict[str, TestingFunction] = PrivateAttr(default_factory=dict)
    _deployments: list[tuple[Path, str]] = PrivateAttr(default_factory=list)

    # =====================================================================
    # Environment
    # =====================================================================

    def environment_create(self, name: str) -> None:
        self._environments.add(name)

    # =====================================================================
    # App
    # =====================================================================

    def app_create(self, name: str) -> AppInterface:
        app_id = f"ap-{uuid.uuid4().hex[:12]}"
        app = TestingApp(app_id=app_id, app_name=name)
        self._apps[name] = app
        return app

    def app_lookup(
        self,
        name: str,
        *,
        create_if_missing: bool = True,
        environment_name: str,
    ) -> AppInterface:
        # Check that the environment exists (or auto-create it for convenience)
        if environment_name not in self._environments:
            if create_if_missing:
                self._environments.add(environment_name)
            else:
                raise ModalProxyNotFoundError(f"Environment not found: {environment_name}")
        key = f"{environment_name}/{name}"
        if key in self._apps:
            return self._apps[key]
        if create_if_missing:
            app_id = f"ap-{uuid.uuid4().hex[:12]}"
            app = TestingApp(app_id=app_id, app_name=name)
            self._apps[key] = app
            return app
        raise ModalProxyNotFoundError(f"App not found: {name}")

    # =====================================================================
    # Image
    # =====================================================================

    def image_debian_slim(self) -> ImageInterface:
        return TestingImage(image_id=f"img-debian-{uuid.uuid4().hex[:8]}")

    def image_from_registry(self, name: str) -> ImageInterface:
        return TestingImage(image_id=f"img-reg-{name.replace(':', '-').replace('/', '-')}-{uuid.uuid4().hex[:8]}")

    def image_from_id(self, image_id: str) -> ImageInterface:
        return TestingImage(image_id=image_id)

    # =====================================================================
    # Sandbox
    # =====================================================================

    def sandbox_create(
        self,
        *,
        image: ImageInterface,
        app: AppInterface,
        timeout: int,
        cpu: float,
        memory: int,
        unencrypted_ports: Sequence[int] = (),
        gpu: str | None = None,
        region: str | None = None,
        cidr_allowlist: Sequence[str] | None = None,
        volumes: Mapping[str, VolumeInterface] | None = None,
    ) -> SandboxInterface:
        sandbox_id = f"sb-{uuid.uuid4().hex[:12]}"
        sandbox = TestingSandbox(sandbox_id=sandbox_id)
        self._sandboxes.append(sandbox)
        return sandbox

    def sandbox_list(self, *, app_id: str) -> list[SandboxInterface]:
        # Return all non-terminated sandboxes
        return [sb for sb in self._sandboxes if not sb._is_terminated]

    def sandbox_from_id(self, sandbox_id: str) -> SandboxInterface:
        for sb in self._sandboxes:
            if sb.sandbox_id == sandbox_id:
                return sb
        raise ModalProxyNotFoundError(f"Sandbox not found: {sandbox_id}")

    # =====================================================================
    # Volume
    # =====================================================================

    def volume_from_name(
        self,
        name: str,
        *,
        create_if_missing: bool = True,
        environment_name: str,
        version: int | None = None,
    ) -> VolumeInterface:
        key = f"{environment_name}/{name}"
        if key in self._volumes:
            return self._volumes[key]
        if not create_if_missing:
            raise ModalProxyNotFoundError(f"Volume not found: {name}")
        vol_dir = self.root_dir / "volumes" / environment_name / name
        vol_dir.mkdir(parents=True, exist_ok=True)
        volume = TestingVolume(root_dir=vol_dir, volume_name=name)
        self._volumes[key] = volume
        return volume

    def volume_list(self, *, environment_name: str) -> list[VolumeInterface]:
        prefix = f"{environment_name}/"
        return [vol for key, vol in self._volumes.items() if key.startswith(prefix)]

    def volume_delete(self, name: str, *, environment_name: str) -> None:
        key = f"{environment_name}/{name}"
        if key not in self._volumes:
            raise ModalProxyNotFoundError(f"Volume not found: {name}")
        volume = self._volumes.pop(key)
        if volume.root_dir.exists():
            shutil.rmtree(volume.root_dir)

    # =====================================================================
    # Secret
    # =====================================================================

    def secret_from_dict(self, values: Mapping[str, str | None]) -> SecretInterface:
        return TestingSecret(values=dict(values))

    # =====================================================================
    # Function
    # =====================================================================

    def function_from_name(
        self,
        name: str,
        *,
        app_name: str,
        environment_name: str | None = None,
    ) -> FunctionInterface:
        key = f"{app_name}/{name}"
        if key in self._functions:
            return self._functions[key]
        raise ModalProxyNotFoundError(f"Function not found: {name} in app {app_name}")

    # =====================================================================
    # CLI
    # =====================================================================

    def deploy(
        self,
        script_path: Path,
        *,
        app_name: str,
        environment_name: str | None = None,
    ) -> None:
        self._deployments.append((script_path, app_name))
        # Register a testing function for each deployment so function_from_name works
        # Use a predictable URL pattern
        # Scan the script for function names (look for @app.function patterns)
        try:
            content = script_path.read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("def ") and "(" in stripped:
                    func_name = stripped[4 : stripped.index("(")]
                    key = f"{app_name}/{func_name}"
                    self._functions[key] = TestingFunction(url=f"https://testing.modal.run/{app_name}/{func_name}")
        except (OSError, ValueError):
            pass

    # =====================================================================
    # Testing helpers
    # =====================================================================

    def cleanup(self) -> None:
        """Terminate all sandboxes and clean up resources."""
        for sandbox in self._sandboxes:
            sandbox.terminate()
        self._sandboxes.clear()

    def get_sandbox_count(self) -> int:
        """Get the number of active (non-terminated) sandboxes."""
        return sum(1 for sb in self._sandboxes if not sb._is_terminated)

    def wait_for_idle(self, timeout: float = 5.0) -> None:
        """Wait for all background processes in all sandboxes to complete."""
        deadline = time.monotonic() + timeout
        for sandbox in self._sandboxes:
            for proc in sandbox._background_processes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    proc.wait(timeout=max(0.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
