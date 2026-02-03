from datetime import datetime
from enum import auto
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Self

from pydantic import Field
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema
from pydantic_core import core_schema

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.ids import RandomId
from imbue.imbue_common.primitives import NonEmptyStr

# === Enums ===


class AgentNameStyle(UpperCaseStrEnum):
    """Style for auto-generated agent names."""

    ENGLISH = auto()
    FANTASY = auto()
    SCIFI = auto()
    PAINTERS = auto()
    AUTHORS = auto()
    ARTISTS = auto()
    MUSICIANS = auto()
    ANIMALS = auto()
    SCIENTISTS = auto()
    DEMONS = auto()


class HostNameStyle(UpperCaseStrEnum):
    """Style for auto-generated host names."""

    ASTRONOMY = auto()
    PLACES = auto()
    CITIES = auto()
    FANTASY = auto()
    SCIFI = auto()
    PAINTERS = auto()
    AUTHORS = auto()
    ARTISTS = auto()
    MUSICIANS = auto()
    SCIENTISTS = auto()


class LogLevel(UpperCaseStrEnum):
    """Log verbosity level."""

    TRACE = auto()
    DEBUG = auto()
    BUILD = auto()
    INFO = auto()
    WARN = auto()
    ERROR = auto()
    NONE = auto()


class IdleMode(UpperCaseStrEnum):
    """Mode for determining when host is considered idle."""

    IO = auto()
    USER = auto()
    AGENT = auto()
    SSH = auto()
    CREATE = auto()
    BOOT = auto()
    START = auto()
    RUN = auto()
    DISABLED = auto()


class ActivitySource(UpperCaseStrEnum):
    """Sources of activity for idle detection."""

    CREATE = auto()
    BOOT = auto()
    START = auto()
    SSH = auto()
    PROCESS = auto()
    AGENT = auto()
    USER = auto()


class BootstrapMode(UpperCaseStrEnum):
    """Bootstrap behavior for missing tools."""

    SILENT = auto()
    WARN = auto()
    FAIL = auto()


class LifecycleHook(UpperCaseStrEnum):
    """Available lifecycle hooks."""

    INITIALIZE = auto()
    ON_CREATE = auto()
    UPDATE_CONTENT = auto()
    POST_CREATE = auto()
    POST_START = auto()
    POST_ATTACH = auto()


class OutputFormat(UpperCaseStrEnum):
    """Output format mode."""

    HUMAN = auto()
    JSON = auto()
    JSONL = auto()


class ErrorBehavior(UpperCaseStrEnum):
    """Behavior when encountering errors during operations."""

    ABORT = auto()
    CONTINUE = auto()


class WorkDirCopyMode(UpperCaseStrEnum):
    """Mode for copying work directory content."""

    COPY = auto()
    CLONE = auto()
    WORKTREE = auto()


# === ID Types ===


class HostState(UpperCaseStrEnum):
    """The lifecycle state of a host."""

    BUILDING = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    PAUSED = auto()
    CRASHED = auto()
    FAILED = auto()
    DESTROYED = auto()


class AgentLifecycleState(UpperCaseStrEnum):
    """The lifecycle state of an agent.

    When the host is running, agents can be in one of the agent-specific states:
    - STOPPED: the agent folder exists but there is no tmux session
    - RUNNING: tmux session exists and the expected process exists in pane 0
    - WAITING: tmux session exists and the process is waiting for input
    - REPLACED: tmux session exists and a different process is in pane 0
    - DONE: the tmux session exists and there is no process under the shell

    When the host is NOT running, the agent inherits the host's state:
    - PAUSED: host became idle and was snapshotted/shut down
    - CRASHED: host shut down unexpectedly without a controlled shutdown
    - DESTROYED: host is gone, resources freed (no snapshots available)
    - FAILED: something went wrong before the host could be created
    - BUILDING: host image is being built
    - STARTING: host is being created and provisioned
    - STOPPING: host is being stopped/snapshotted
    """

    # Agent-specific states (when host IS running)
    STOPPED = auto()
    RUNNING = auto()
    WAITING = auto()
    REPLACED = auto()
    DONE = auto()

    # Host states that agents inherit (when host is NOT running)
    PAUSED = auto()
    CRASHED = auto()
    DESTROYED = auto()
    FAILED = auto()
    BUILDING = auto()
    STARTING = auto()
    STOPPING = auto()


class AgentId(RandomId):
    """Unique identifier for an agent."""

    PREFIX = "agent"


class HostId(RandomId):
    """Unique identifier for a host."""

    PREFIX = "host"


class SnapshotId(NonEmptyStr):
    """Unique identifier for a snapshot."""


class VolumeId(RandomId):
    """Unique identifier for a volume."""

    PREFIX = "vol"


class ProviderInstanceName(NonEmptyStr):
    """Name of a provider instance."""


LOCAL_PROVIDER_NAME = ProviderInstanceName("local")


class ProviderBackendName(NonEmptyStr):
    """Name of a provider backend."""


class AgentName(NonEmptyStr):
    """Human-readable name for an agent."""


class HostName(NonEmptyStr):
    """Human-readable name for a host."""

    @property
    def provider_name(self) -> ProviderInstanceName | None:
        """Extract the provider name if specified as 'host_name.provider_name'."""
        parts = self.split(".")
        if len(parts) == 2:
            return ProviderInstanceName(parts[1])
        return None

    @property
    def short_name(self) -> str:
        """Get the short host name without the provider suffix."""
        parts = self.split(".")
        return parts[0]


class AgentTypeName(NonEmptyStr):
    """Type name for an agent (e.g., claude, codex)."""


class PluginName(NonEmptyStr):
    """Name of a plugin."""


class Permission(NonEmptyStr):
    """Permission identifier for agent access control."""


class ImageReference(NonEmptyStr):
    """Reference to a container or VM image."""


class CommandString(NonEmptyStr):
    """Command string to be executed."""


class SnapshotName(str):
    """Human-readable name for a snapshot."""

    def __new__(cls, value: str) -> Self:
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )


class HostReference(FrozenModel):
    """Lightweight reference to a host for display and identification purposes."""

    host_id: HostId
    host_name: HostName
    provider_name: ProviderInstanceName


class AgentReference(FrozenModel):
    """Lightweight reference to an agent with certified data from data.json.

    This class provides access to agent data that can be retrieved without requiring
    the host to be online. The certified_data field contains the raw data.json contents,
    and property methods provide convenient typed access to common fields.
    """

    host_id: HostId
    agent_id: AgentId
    agent_name: AgentName
    provider_name: ProviderInstanceName
    certified_data: Mapping[str, Any] = Field(default_factory=dict)

    @property
    def agent_type(self) -> "AgentTypeName | None":
        """Return the agent type, or None if not available."""
        type_value = self.certified_data.get("type")
        if type_value is not None:
            return AgentTypeName(type_value)
        return None

    @property
    def work_dir(self) -> Path | None:
        """Return the agent's working directory, or None if not available."""
        work_dir_value = self.certified_data.get("work_dir")
        if work_dir_value is not None:
            return Path(work_dir_value)
        return None

    @property
    def command(self) -> "CommandString | None":
        """Return the command used to start this agent, or None if not available."""
        command_value = self.certified_data.get("command")
        if command_value is not None:
            return CommandString(command_value)
        return None

    @property
    def create_time(self) -> datetime | None:
        """Return the agent creation time, or None if not available."""
        create_time_value = self.certified_data.get("create_time")
        if create_time_value is not None:
            if isinstance(create_time_value, datetime):
                return create_time_value
            # Handle ISO format string
            return datetime.fromisoformat(create_time_value)
        return None

    @property
    def start_on_boot(self) -> bool:
        """Return whether this agent should start automatically on host boot."""
        return bool(self.certified_data.get("start_on_boot", False))

    @property
    def permissions(self) -> tuple["Permission", ...]:
        """Return the list of permissions assigned to this agent."""
        permissions_value = self.certified_data.get("permissions", [])
        return tuple(Permission(p) for p in permissions_value)
