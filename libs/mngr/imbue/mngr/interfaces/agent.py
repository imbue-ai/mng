from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentLifecycleState
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import Permission

# this is the only place where it is acceptable to use the TYPE_CHECKING flag
if TYPE_CHECKING:
    from imbue.mngr.interfaces.host import HostInterface


class AgentStatus(FrozenModel):
    """Agent status information."""

    line: str = Field(description="Single line summary")
    full: str = Field(description="Full markdown description")
    html: str | None = Field(default=None, description="HTML status report")


class AgentInterface(MutableModel, ABC):
    """Interface for agent implementations."""

    id: AgentId = Field(frozen=True, description="Unique identifier for this agent")
    name: AgentName = Field(description="Human-readable agent name")
    agent_type: AgentTypeName = Field(frozen=True, description="Type of agent (claude, codex, etc.)")
    work_dir: Path = Field(frozen=True, description="Working directory for this agent")
    create_time: datetime = Field(frozen=True, description="When the agent was created")
    host_id: HostId = Field(description="ID of the host this agent runs on")
    mngr_ctx: MngrContext = Field(frozen=True, repr=False, description="Mngr context")
    agent_config: AgentTypeConfig = Field(frozen=True, repr=False, description="Agent type config")

    @abstractmethod
    def get_host(self) -> HostInterface:
        """Return the host this agent runs on."""
        ...

    @abstractmethod
    def assemble_command(
        self,
        host: HostInterface,
        agent_args: tuple[str, ...],
        command_override: CommandString | None,
    ) -> CommandString | None:
        """Assemble the full command to execute for this agent, or return None if no command is defined."""
        ...

    # =========================================================================
    # Certified Field Getters/Setters
    # =========================================================================

    @abstractmethod
    def get_command(self) -> CommandString:
        """Return the command used to start this agent."""
        ...

    @abstractmethod
    def get_permissions(self) -> list[Permission]:
        """Return the list of permissions assigned to this agent."""
        ...

    @abstractmethod
    def set_permissions(self, value: Sequence[Permission]) -> None:
        """Set the list of permissions for this agent."""
        ...

    @abstractmethod
    def get_is_start_on_boot(self) -> bool:
        """Return whether this agent should start automatically on host boot."""
        ...

    @abstractmethod
    def set_is_start_on_boot(self, value: bool) -> None:
        """Set whether this agent should start automatically on host boot."""
        ...

    # =========================================================================
    # Interaction
    # =========================================================================

    @abstractmethod
    def is_running(self) -> bool:
        """Return whether the agent process is currently running."""
        ...

    @abstractmethod
    def get_lifecycle_state(self) -> AgentLifecycleState:
        """Return the lifecycle state of this agent (stopped, running, waiting, replaced, or done)."""
        ...

    @abstractmethod
    def get_initial_message(self) -> str | None:
        """Return the initial message to send to the agent on start, or None if not set."""
        ...

    @abstractmethod
    def send_message(self, message: str) -> None:
        """Send a message to the running agent via its stdin."""
        ...

    # =========================================================================
    # Status (Reported)
    # =========================================================================

    @abstractmethod
    def get_reported_url(self) -> str | None:
        """Return the agent's self-reported URL, or None if not set."""
        ...

    @abstractmethod
    def get_reported_start_time(self) -> datetime | None:
        """Return the agent's self-reported start time, or None if not set."""
        ...

    @abstractmethod
    def get_reported_status_markdown(self) -> str | None:
        """Return the agent's self-reported status in markdown format, or None if not set."""
        ...

    @abstractmethod
    def get_reported_status_html(self) -> str | None:
        """Return the agent's self-reported status in HTML format, or None if not set."""
        ...

    @abstractmethod
    def get_reported_status(self) -> AgentStatus | None:
        """Return the agent's self-reported status, or None if not available."""
        ...

    # =========================================================================
    # Activity
    # =========================================================================

    @abstractmethod
    def get_reported_activity_time(self, activity_type: ActivitySource) -> datetime | None:
        """Return the last activity time for a given activity source, or None if not recorded."""
        ...

    @abstractmethod
    def record_activity(self, activity_type: ActivitySource) -> None:
        """Record activity of a given type for this agent at the current time."""
        ...

    @abstractmethod
    def get_reported_activity_record(self, activity_type: ActivitySource) -> str | None:
        """Return the raw activity record for a given type, or None if not found."""
        ...

    # =========================================================================
    # Plugin Data (Certified)
    # =========================================================================

    @abstractmethod
    def get_plugin_data(self, plugin_name: str) -> dict[str, Any]:
        """Return certified plugin data for a given plugin, or empty dict if not found."""
        ...

    @abstractmethod
    def set_plugin_data(self, plugin_name: str, data: dict[str, Any]) -> None:
        """Set certified plugin data for a given plugin."""
        ...

    # =========================================================================
    # Plugin Data (Reported)
    # =========================================================================

    @abstractmethod
    def get_reported_plugin_file(self, plugin_name: str, filename: str) -> str:
        """Read and return the contents of a reported plugin file."""
        ...

    @abstractmethod
    def set_reported_plugin_file(self, plugin_name: str, filename: str, data: str) -> None:
        """Write data to a reported plugin file."""
        ...

    @abstractmethod
    def list_reported_plugin_files(self, plugin_name: str) -> list[str]:
        """Return a list of all reported file names for a given plugin."""
        ...

    # =========================================================================
    # Environment
    # =========================================================================

    @abstractmethod
    def get_env_vars(self) -> dict[str, str]:
        """Return all environment variables for this agent."""
        ...

    @abstractmethod
    def set_env_vars(self, env: Mapping[str, str]) -> None:
        """Set all environment variables for this agent, replacing any existing ones."""
        ...

    @abstractmethod
    def get_env_var(self, key: str) -> str | None:
        """Return a single environment variable by key, or None if not found."""
        ...

    @abstractmethod
    def set_env_var(self, key: str, value: str) -> None:
        """Set a single environment variable for this agent."""
        ...

    # =========================================================================
    # Computed Properties
    # =========================================================================

    @property
    @abstractmethod
    def runtime_seconds(self) -> float | None:
        """Return how many seconds the agent has been running, or None if not started."""
        ...
