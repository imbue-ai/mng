class SculptorWebError(Exception):
    """Base exception for all sculptor_web errors."""

    ...


class AgentListingError(SculptorWebError, RuntimeError):
    """Raised when listing agents fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Failed to list agents: {message}")
