class ZygoteError(Exception):
    """Base error for the zygote agent framework."""


class ToolExecutionError(ZygoteError):
    """Raised when a tool fails to execute."""


class InnerDialogError(ZygoteError):
    """Raised when the inner dialog loop encounters an error."""


class ChatResponseError(ZygoteError):
    """Raised when chat response generation fails."""


class CompactionError(ZygoteError):
    """Raised when conversation history compaction fails."""
