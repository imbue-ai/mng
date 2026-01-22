from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema
from pyinfra.api import Host as PyinfraHost

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonNegativeInt
from imbue.mngr.errors import ParseSpecError
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import HostId
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
                "connector_cls": {"type": "string", "description": "The connector class name"},
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


class CertifiedHostData(FrozenModel):
    """Certified data stored in the host's data.json file."""

    idle_mode: IdleMode = Field(
        default=IdleMode.AGENT,
        description="Mode for determining when host is considered idle",
    )
    idle_timeout_seconds: int = Field(
        default=3600,
        description="Maximum idle time before stopping",
        validation_alias="max_idle_seconds",
        serialization_alias="max_idle_seconds",
    )
    activity_sources: tuple[ActivitySource, ...] = Field(
        default_factory=lambda: tuple(ActivitySource),
        description="Activity sources that count toward keeping host active",
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


class HostInfo(FrozenModel):
    """Information about a host/machine."""

    id: HostId = Field(description="Host ID")
    name: str = Field(description="Host name")
    provider_name: ProviderInstanceName = Field(description="Provider that owns the host")


class FileTransferSpec(FrozenModel):
    """Specification for a file transfer during agent provisioning.

    Used by plugins to declare files that should be copied from the local machine
    to the remote host before other provisioning steps run.

    Note: Currently only supports individual files, not directories.
    """

    local_path: Path = Field(description="Path to the file on the local machine")
    remote_path: Path = Field(
        description="Destination path on the remote host. Relative paths are relative to work_dir"
    )
    is_required: bool = Field(
        description="If True, provisioning fails if local file doesn't exist. If False, skipped if missing."
    )
