class ChangelingError(Exception):
    """Base exception for all changeling errors."""

    ...


class ChangelingNotFoundError(ChangelingError, KeyError):
    """Raised when a changeling cannot be found by name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Changeling '{name}' not found")


class ChangelingAlreadyExistsError(ChangelingError, ValueError):
    """Raised when attempting to add a changeling with a name that already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Changeling '{name}' already exists")


class ChangelingConfigError(ChangelingError):
    """Raised when changeling configuration is invalid or cannot be loaded."""

    ...


class ChangelingDeployError(ChangelingError):
    """Raised when deploying a changeling to Modal fails."""

    ...


class ChangelingRunError(ChangelingError, RuntimeError):
    """Raised when a changeling fails to run (nonzero exit code from mngr create)."""

    ...
