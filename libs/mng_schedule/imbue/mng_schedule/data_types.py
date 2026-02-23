from enum import auto

from pydantic import Field

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.frozen_model import FrozenModel


class ScheduledMngCommand(UpperCaseStrEnum):
    """The mng commands that can be scheduled."""

    CREATE = auto()
    START = auto()
    MESSAGE = auto()
    EXEC = auto()


class VerifyMode(UpperCaseStrEnum):
    """Controls post-deploy verification behavior."""

    NONE = auto()
    QUICK = auto()
    FULL = auto()


class ScheduleTriggerDefinition(FrozenModel):
    """A scheduled trigger that runs an mng command on a cron schedule."""

    name: str = Field(description="Unique name for this scheduled trigger")
    command: ScheduledMngCommand = Field(description="Which mng command to run")
    args: str = Field(default="", description="Arguments to pass to the mng command")
    schedule_cron: str = Field(description="Cron expression defining when the command runs")
    provider: str = Field(description="Provider on which to run the scheduled command (e.g. 'modal')")
    is_enabled: bool = Field(default=True, description="Whether this schedule is active")
    git_image_hash: str = Field(description="Git commit SHA for packaging project code into the image")
