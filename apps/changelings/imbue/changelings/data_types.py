from pydantic import Field

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl
from imbue.imbue_common.frozen_model import FrozenModel


class ChangelingDefinition(FrozenModel):
    """A configured changeling -- an autonomous agent that runs on a schedule."""

    name: ChangelingName = Field(description="Unique name for this changeling")
    template: ChangelingTemplateName = Field(description="Which built-in template to use")
    schedule: CronSchedule = Field(description="Cron expression for when this changeling runs")
    repo: GitRepoUrl = Field(description="Git repository URL to operate on")
    branch: str = Field(default="main", description="Base branch to work from")
    message: str | None = Field(
        default=None, description="Custom initial message to send to the agent (overrides template default)"
    )
    agent_type: str = Field(default="claude", description="The mngr agent type to use")
    extra_mngr_args: str = Field(default="", description="Additional arguments to pass to mngr create")
    env_vars: dict[str, str] = Field(default_factory=dict, description="Environment variables to set for the agent")
    is_enabled: bool = Field(default=True, description="Whether this changeling is currently active")


class ChangelingConfig(FrozenModel):
    """Top-level configuration containing all registered changelings."""

    changeling_by_name: dict[ChangelingName, ChangelingDefinition] = Field(
        default_factory=dict,
        description="All registered changelings indexed by name",
    )
