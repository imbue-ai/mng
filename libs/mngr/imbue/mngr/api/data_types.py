from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic import computed_field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.config.data_types import EnvVar
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import ActivityConfig
from imbue.mngr.interfaces.data_types import BuildCacheInfo
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.interfaces.data_types import LogFileInfo
from imbue.mngr.interfaces.data_types import SnapshotInfo
from imbue.mngr.interfaces.data_types import VolumeInfo
from imbue.mngr.interfaces.data_types import WorkDirInfo
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import IdleMode
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotName


class CreateAgentResult(FrozenModel):
    """Result of creating an agent."""

    agent: AgentInterface = Field(description="The created agent")
    host: OnlineHostInterface = Field(description="The host running the agent")


class SourceLocation(FrozenModel):
    """Specifies where to get source data from.

    Can be a local path, an agent on a host, or a combination. At minimum,
    either path or agent_name must be specified.
    """

    path: Path | None = Field(
        default=None,
        description="Local or remote path to the source directory",
    )
    agent_id: AgentId | None = Field(
        default=None,
        description="Source agent ID (for cloning from an existing agent)",
    )
    agent_name: AgentName | None = Field(
        default=None,
        description="Source agent name (alternative to ID)",
    )
    host_id: HostId | None = Field(
        default=None,
        description="Host where the source agent/path resides",
    )
    host_name: HostName | None = Field(
        default=None,
        description="Host name (alternative to ID)",
    )

    @computed_field
    @property
    def is_from_agent(self) -> bool:
        """Returns True if this source is from an existing agent."""
        return self.agent_id is not None or self.agent_name is not None


class NewHostBuildOptions(FrozenModel):
    """Options for building a new host image."""

    snapshot: SnapshotName | None = Field(
        default=None,
        description="Use existing snapshot instead of building",
    )
    context_path: Path | None = Field(
        default=None,
        description="Build context directory [default: local .git root]",
    )
    build_args: tuple[str, ...] = Field(
        default=(),
        description="Arguments for the build command",
    )
    start_args: tuple[str, ...] = Field(
        default=(),
        description="Arguments for the start command",
    )


class HostEnvironmentOptions(FrozenModel):
    """Environment variable configuration for a host."""

    env_vars: tuple[EnvVar, ...] = Field(
        default=(),
        description="Environment variables to set (KEY=VALUE)",
    )
    env_files: tuple[Path, ...] = Field(
        default=(),
        description="Files to load environment variables from",
    )
    known_hosts: tuple[str, ...] = Field(
        default=(),
        description="SSH known_hosts entries to add to the host (for outbound SSH connections)",
    )


class HostLifecycleOptions(FrozenModel):
    """Lifecycle and idle detection options for the host.

    These options control when a host is considered idle and should be shut down.
    All fields are optional; when None, provider defaults are used.
    """

    idle_timeout_seconds: int | None = Field(
        default=None,
        description="Shutdown after idle for N seconds (None for provider default)",
    )
    idle_mode: IdleMode | None = Field(
        default=None,
        description="When to consider host idle (None for provider default)",
    )
    activity_sources: tuple[ActivitySource, ...] | None = Field(
        default=None,
        description="Activity sources for idle detection (None for provider default)",
    )

    def to_activity_config(
        self,
        default_idle_timeout_seconds: int,
        default_idle_mode: IdleMode,
        default_activity_sources: tuple[ActivitySource, ...],
    ) -> ActivityConfig:
        """Convert to ActivityConfig, using provided defaults for None values."""
        return ActivityConfig(
            idle_timeout_seconds=self.idle_timeout_seconds
            if self.idle_timeout_seconds is not None
            else default_idle_timeout_seconds,
            idle_mode=self.idle_mode if self.idle_mode is not None else default_idle_mode,
            activity_sources=self.activity_sources if self.activity_sources is not None else default_activity_sources,
        )


class NewHostOptions(FrozenModel):
    """Options for creating a new host."""

    provider: ProviderInstanceName = Field(
        description="Provider to use for creating the host (docker, modal, local, ...)",
    )
    name: HostName = Field(
        description="Name for the new host",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Metadata tags for the host",
    )
    build: NewHostBuildOptions = Field(
        default_factory=NewHostBuildOptions,
        description="Build options for the host image",
    )
    environment: HostEnvironmentOptions = Field(
        default_factory=HostEnvironmentOptions,
        description="Environment variable configuration",
    )
    lifecycle: HostLifecycleOptions = Field(
        default_factory=HostLifecycleOptions,
        description="Lifecycle and idle detection options",
    )


class ConnectionOptions(FrozenModel):
    """Options for connecting to an agent after creation."""

    is_reconnect: bool = Field(
        default=True,
        description="Automatically reconnect if connection is dropped",
    )
    is_interactive: bool | None = Field(
        default=None,
        description="Enable interactive mode (None means auto-detect TTY)",
    )
    message: str | None = Field(
        default=None,
        description="Message to send after connecting to agent",
    )
    retry_count: int = Field(
        default=3,
        description="Number of connection retries",
    )
    retry_delay: str = Field(
        default="5s",
        description="Delay between retries (e.g., 5s, 1m)",
    )
    attach_command: str | None = Field(
        default=None,
        description="Command to run instead of attaching to main session",
    )
    is_unknown_host_allowed: bool = Field(
        default=False,
        description="Whether to allow connecting to hosts with unknown SSH keys",
    )


class GcResourceTypes(FrozenModel):
    """Specifies which resource types to garbage collect."""

    is_machines: bool = Field(default=False, description="Clean idle machines with no agents")
    is_snapshots: bool = Field(default=False, description="Clean orphaned snapshots")
    is_volumes: bool = Field(default=False, description="Clean orphaned volumes")
    is_work_dirs: bool = Field(default=False, description="Clean orphaned work directories")
    is_logs: bool = Field(default=False, description="Clean old log files")
    is_build_cache: bool = Field(default=False, description="Clean build cache entries")


class GcResult(MutableModel):
    """Aggregated results of garbage collection across all resource types."""

    work_dirs_destroyed: list[WorkDirInfo] = Field(
        default_factory=list,
        description="Work directories that were destroyed",
    )
    machines_destroyed: list[HostInfo] = Field(
        default_factory=list,
        description="Machines that were destroyed",
    )
    snapshots_destroyed: list[SnapshotInfo] = Field(
        default_factory=list,
        description="Snapshots that were destroyed",
    )
    volumes_destroyed: list[VolumeInfo] = Field(
        default_factory=list,
        description="Volumes that were destroyed",
    )
    logs_destroyed: list[LogFileInfo] = Field(
        default_factory=list,
        description="Log files that were destroyed",
    )
    build_cache_destroyed: list[BuildCacheInfo] = Field(
        default_factory=list,
        description="Build cache entries that were destroyed",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered during garbage collection",
    )


class OnBeforeCreateArgs(FrozenModel):
    """Arguments passed to and returned from the on_before_create hook.

    This bundles all the modifiable arguments to the create() API function.
    Plugins can return a modified copy of this object to change the create behavior.

    Note: source_host is not included because it represents the resolved source
    location which should not typically be modified by plugins. The source_path
    within the resolved location can still be modified if needed via the path field.
    """

    model_config = {"arbitrary_types_allowed": True}

    target_host: OnlineHostInterface | NewHostOptions = Field(
        description="The target host (or options to create one) for the agent"
    )
    agent_options: CreateAgentOptions = Field(description="Options for creating the agent")
    create_work_dir: bool = Field(description="Whether to create a work directory")
