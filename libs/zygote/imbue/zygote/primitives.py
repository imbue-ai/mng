from enum import auto

from imbue.imbue_common.enums import UpperCaseStrEnum
from imbue.imbue_common.ids import RandomId
from imbue.imbue_common.primitives import NonEmptyStr


class ThreadId(RandomId):
    """Unique identifier for a chat thread."""

    PREFIX = "thread"


class MessageId(RandomId):
    """Unique identifier for a message within a thread."""

    PREFIX = "msg"


class NotificationId(RandomId):
    """Unique identifier for a notification to the inner dialog."""

    PREFIX = "notif"


class MemoryKey(NonEmptyStr):
    """Key for the agent's persistent memory store."""


class ModelName(NonEmptyStr):
    """Name of a Claude model (e.g., 'claude-sonnet-4-5-20250514')."""


class MessageRole(UpperCaseStrEnum):
    """Role of a message sender."""

    USER = auto()
    ASSISTANT = auto()


class NotificationSource(UpperCaseStrEnum):
    """Source of a notification to the inner dialog agent."""

    USER_MESSAGE = auto()
    SUB_AGENT_COMPLETED = auto()
    SYSTEM = auto()
