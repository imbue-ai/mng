class ChangelingError(Exception):
    """Base exception for all changelings errors."""

    ...


class AgentAlreadyExistsError(ChangelingError):
    """Raised when attempting to deploy a changeling with a name that already exists."""

    ...


class SigningKeyError(ChangelingError):
    """Raised when the cookie signing key cannot be loaded or created."""

    ...


class GitCloneError(ChangelingError):
    """Raised when git clone fails."""

    ...
