from enum import auto

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.primitives import NonEmptyStr


class ChangelingName(NonEmptyStr):
    """The unique name identifying a changeling (e.g., 'fixme-fairy', 'test-troll')."""

    ...


class CronSchedule(NonEmptyStr):
    """A cron expression defining when a changeling runs (e.g., '0 3 * * *' for 3am daily)."""

    ...


class GitRepoUrl(NonEmptyStr):
    """A git repository URL (HTTPS or SSH) that a changeling targets."""

    ...


class LogLevel(UpperCaseStrEnum):
    """Log verbosity level."""

    TRACE = auto()
    DEBUG = auto()
    BUILD = auto()
    INFO = auto()
    WARN = auto()
    ERROR = auto()
    NONE = auto()


class OutputFormat(UpperCaseStrEnum):
    """Output format mode."""

    HUMAN = auto()
    JSON = auto()
    JSONL = auto()
