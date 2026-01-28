from enum import auto
from typing import Any
from typing import Self

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


class UncommittedChangesMode(UpperCaseStrEnum):
    """Mode for handling uncommitted changes in the host repo when pulling files."""

    STASH = auto()
    CLOBBER = auto()
    MERGE = auto()
    FAIL = auto()


# === ID Types ===


class HostState(UpperCaseStrEnum):
    """The lifecycle state of a host."""

    BUILDING = auto()
    STARTING = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    DESTROYED = auto()


class AgentLifecycleState(UpperCaseStrEnum):
    """The lifecycle state of an agent."""

    STOPPED = auto()
    RUNNING = auto()
    WAITING = auto()
    REPLACED = auto()
    DONE = auto()


class AgentId(RandomId):
    """Unique identifier for an agent."""

    PREFIX = "agent"


class HostId(RandomId):
    """Unique identifier for a host."""

    PREFIX = "host"


class SnapshotId(RandomId):
    """Unique identifier for a snapshot."""

    PREFIX = "snap"


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
    """Lightweight reference to an agent for display and identification purposes."""

    host_id: HostId
    agent_id: AgentId
    agent_name: AgentName
    provider_name: ProviderInstanceName
