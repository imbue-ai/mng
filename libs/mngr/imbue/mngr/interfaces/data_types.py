from __future__ import annotations

from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from pydantic import Field
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from pyinfra.api import Host as PyinfraHost

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonNegativeInt
from imbue.mngr.errors import InvalidRelativePathError
from imbue.mngr.errors import ParseSpecError
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostState
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.primitives import VolumeId


class PyinfraConnector:
    """Pydantic-serializable wrapper for pyinfra Host objects.

    Stores the actual pyinfra Host instance while providing serialization
    based on the host name and connector class name. Access the underlying
    pyinfra Host via the `host` property for all operations.
    """

    __slots__ = ("_host",)

    def __init__(self, host: "PyinfraHost") -> None:
        self._host = host

    @property
    def host(self) -> "PyinfraHost":
        """The underlying pyinfra Host instance."""
        return self._host

    @property
    def name(self) -> str:
        """The pyinfra host name."""
        return self._host.name

    @property
    def connector_cls_name(self) -> str:
        """The name of the connector class (e.g., 'LocalConnector', 'SSHConnector')."""
        return self._host.connector_cls.__name__

    def __repr__(self) -> str:
        return f"PyinfraConnector(name={self.name!r}, connector={self.connector_cls_name})"

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        """Define how Pydantic should serialize/validate this type."""
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize,
                info_arg=False,
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        _core_schema: core_schema.CoreSchema,
        handler: Any,
    ) -> dict[str, Any]:
        """Define the JSON schema for this type."""
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The pyinfra host name"},
                "connector_cls": {
                    "type": "string",
                    "description": "The connector class name",
                },
            },
            "required": ["name", "connector_cls"],
        }

    @classmethod
    def _validate(cls, value: Any) -> "PyinfraConnector":
        if isinstance(value, cls):
            return value
        # Allow constructing from a pyinfra Host directly
        if isinstance(value, PyinfraHost):
            return cls(value)
        raise ParseSpecError(f"Expected PyinfraConnector or pyinfra Host, got {type(value)}")

    def _serialize(self) -> dict[str, str]:
        return {
            "name": self.name,
            "connector_cls": self.connector_cls_name,
        }


class CommandResult(FrozenModel):
    """Result of executing a command on a host."""

    stdout: str = Field(description="Standard output from the command")
    stderr: str = Field(description="Standard error from the command")
    success: bool = Field(description="True if the command succeeded (had an expected exit code)")


class CpuResources(FrozenModel):
    """CPU resource information for a host."""

    count: int = Field(description="Number of CPUs allocated to the host")
    frequency_ghz: float | None = Field(
        default=None,
        description="CPU frequency in GHz (None if not reported by provider)",
    )


class GpuResources(FrozenModel):
    """GPU resource information for a host."""

    count: int = Field(default=0, description="Number of GPUs allocated to the host")
    model: str | None = Field(
        default=None,
        description="GPU model name (e.g., 'NVIDIA A100')",
    )
    memory_gb: float | None = Field(
        default=None,
        description="GPU memory in GB per GPU",
    )


class HostResources(FrozenModel):
    """Resource allocation for a host.

    These values are reported by the provider and represent what has been
    allocated to the host, not necessarily what is currently in use.
    """

    cpu: CpuResources = Field(description="CPU resources")
    memory_gb: float = Field(description="Allocated memory in GB")
    disk_gb: float | None = Field(
        default=None,
        description="Allocated disk space in GB (None if not reported)",
    )
    gpu: GpuResources | None = Field(
        default=None,
        description="GPU resources (None if no GPU allocated)",
    )


class ActivityConfig(FrozenModel):
    """Configuration for host activity detection and idle timeout."""

    idle_mode: IdleMode = Field(description="Mode for determining when host is considered idle")
    idle_timeout_seconds: int = Field(description="Maximum idle time before stopping")
    activity_sources: tuple[ActivitySource, ...] = Field(
        default_factory=lambda: tuple(ActivitySource),
        description="Activity sources that count toward keeping host active",
    )


class HostConfig(FrozenModel):
    pass


class SnapshotRecord(FrozenModel):
    """Snapshot metadata so that a host can be resumed"""

    id: str = Field(description="Image ID (in whatever format the provider uses)")
    name: str = Field(description="Human-readable name")
    created_at: str = Field(description="ISO format timestamp")


class CertifiedHostData(FrozenModel):
    """Certified data stored in the host's data.json file."""

    # FIXME: make this field a derived property--it's fully derivable from activity_sources
    #  Once that is done, remove the idle_mode field from ActivytConfig as well (again, derivable)
    #  The only place this mode was supposed to exist was at the interface layer, as a way of conveniently
    #  allowing a user to specify common sets of activity types from the CLI. Nothing else should know about IdleMode
    idle_mode: IdleMode = Field(
        default=IdleMode.IO,
        description="Mode for determining when host is considered idle",
    )
    idle_timeout_seconds: int = Field(
        default=3600,
        description="Maximum idle time before stopping",
    )
    activity_sources: tuple[ActivitySource, ...] = Field(
        default_factory=lambda: tuple(ActivitySource),
        description="Activity sources that count toward keeping host active",
    )
    max_host_age: int | None = Field(
        default=None,
        description="Maximum host age in seconds from boot before shutdown (used by providers with hard timeouts)",
    )
    plugin: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Plugin-specific certified data indexed by plugin name",
    )
    image: str | None = Field(
        default=None,
        description="Image reference used to create the host",
    )
    generated_work_dirs: tuple[str, ...] = Field(
        default_factory=tuple,
        description="List of work directories that were generated by mngr for agents on this host",
    )
    host_id: str = Field(description="Unique identifier for the host")
    host_name: str = Field(description="Human-readable name")
    user_tags: dict[str, str] = Field(default_factory=dict, description="User-defined tags")
    snapshots: list[SnapshotRecord] = Field(default_factory=list, description="List of snapshots")
    state: HostState | None = Field(
        default=None,
        description="Host state (e.g., FAILED for hosts that failed during creation)",
    )
    stop_reason: str | None = Field(
        default=None,
        description="Reason for last shutdown: 'PAUSED' (idle), 'STOPPED' (user requested), or None (crashed)",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Reason for failure if the host failed during creation",
    )
    build_log: str | None = Field(
        default=None,
        description="Build log output if the host failed during creation",
    )


class SnapshotInfo(FrozenModel):
    """Information about a snapshot."""

    id: SnapshotId = Field(description="Unique identifier for the snapshot")
    name: SnapshotName = Field(description="Human-readable name")
    created_at: datetime = Field(description="When the snapshot was created")
    size_bytes: int | None = Field(
        default=None,
        description="Size in bytes (None if provider doesn't report size)",
    )
    recency_idx: int = Field(
        default=0,
        description="Snapshot recency within host (0 = most recent, incrementing for older snapshots)",
    )


class VolumeInfo(FrozenModel):
    """Information about a volume."""

    volume_id: VolumeId = Field(description="Unique identifier")
    name: str = Field(description="Human-readable name")
    size_bytes: int = Field(description="Size in bytes")
    created_at: datetime = Field(description="Creation timestamp")
    host_id: HostId | None = Field(default=None, description="Associated host, if any")
    tags: dict[str, str] = Field(default_factory=dict, description="Provider tags")


class SizeBytes(NonNegativeInt):
    """Size in bytes. Must be >= 0."""


class WorkDirInfo(FrozenModel):
    """Information about a work directory to be cleaned."""

    path: Path = Field(description="Path to the work directory")
    size_bytes: SizeBytes = Field(default=SizeBytes(0), description="Size in bytes")
    host_id: HostId = Field(description="Host ID this work dir belongs to")
    provider_name: ProviderInstanceName = Field(description="Provider that owns the host")
    is_local: bool = Field(description="Whether this resource is on the local host")
    created_at: datetime = Field(description="When the work directory was created")


class LogFileInfo(FrozenModel):
    """Information about a log file to be cleaned."""

    path: Path = Field(description="Path to the log file")
    size_bytes: SizeBytes = Field(default=SizeBytes(0), description="Size in bytes")
    created_at: datetime = Field(description="When the log file was created")


class BuildCacheInfo(FrozenModel):
    """Information about a build cache entry to be cleaned."""

    path: Path = Field(description="Path to the build cache directory")
    size_bytes: SizeBytes = Field(default=SizeBytes(0), description="Size in bytes")
    created_at: datetime = Field(description="When the cache entry was created")


class SSHInfo(FrozenModel):
    """SSH connection information for a remote host."""

    user: str = Field(description="SSH username")
    host: str = Field(description="SSH hostname")
    port: int = Field(description="SSH port")
    key_path: Path = Field(description="Path to SSH private key")
    command: str = Field(description="Full SSH command to connect")


class HostInfo(FrozenModel):
    """Information about a host/machine."""

    id: HostId = Field(description="Host ID")
    name: str = Field(description="Host name")
    provider_name: ProviderInstanceName = Field(description="Provider that owns the host")

    # Extended fields (all optional)
    state: HostState | None = Field(default=None, description="Current host state (running, stopped, etc.)")
    image: str | None = Field(default=None, description="Host image (Docker image name, Modal image ID, etc.)")
    tags: dict[str, str] = Field(default_factory=dict, description="Metadata tags for the host")
    boot_time: datetime | None = Field(default=None, description="When the host was last started")
    uptime_seconds: float | None = Field(default=None, description="How long the host has been running")
    resource: HostResources | None = Field(default=None, description="Resource limits for the host")
    ssh: SSHInfo | None = Field(default=None, description="SSH access details (remote hosts only)")
    snapshots: list[SnapshotInfo] = Field(default_factory=list, description="List of available snapshots")
    is_locked: bool | None = Field(
        default=None,
        description="Whether the host is currently locked for an operation",
    )
    locked_time: datetime | None = Field(default=None, description="When the host was locked")
    plugin: dict[str, Any] = Field(default_factory=dict, description="Plugin-defined fields")
    failure_reason: str | None = Field(
        default=None,
        description="Reason for failure if the host failed during creation",
    )
    build_log: str | None = Field(
        default=None,
        description="Build log output if the host failed during creation",
    )


class RelativePath(PurePosixPath):
    """A path that must be relative (not absolute).

    Inherits from PurePosixPath to provide full path manipulation capabilities.
    Uses POSIX path semantics since agent paths are always on remote Linux hosts.
    """

    def __new__(cls, *args: str | Path) -> "RelativePath":
        instance = super().__new__(cls, *args)
        if instance.is_absolute():
            raise InvalidRelativePathError(str(instance))
        return instance

    @classmethod
    def _validate(cls, value: Any) -> "RelativePath":
        """Validate and convert input to RelativePath."""
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, Path, PurePosixPath)):
            return cls(value)
        raise ParseSpecError(f"Expected str, Path, or RelativePath, got {type(value)}")

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.to_string_ser_schema(),
        )


class FileTransferSpec(FrozenModel):
    """Specification for a file transfer during agent provisioning.

    Used by plugins to declare files that should be copied from the local machine
    to the agent work_dir before other provisioning steps run.

    Note: Currently only supports individual files, not directories.
    """

    local_path: Path = Field(description="Path to the file on the local machine")
    agent_path: RelativePath = Field(
        description="Destination path on the agent host. Must be a relative path (relative to work_dir)"
    )
    is_required: bool = Field(
        description="If True, provisioning fails if local file doesn't exist. If False, skipped if missing."
    )
