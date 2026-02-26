class ChangelingError(Exception):
    """Base exception for all changelings errors."""

    ...


class InvalidOneTimeCodeError(ChangelingError, ValueError):
    """Raised when a one-time code is invalid, already used, or revoked."""

    ...


class AgentNotAuthenticatedError(ChangelingError):
    """Raised when a request lacks valid authentication for an agent."""

    ...


class SigningKeyError(ChangelingError):
    """Raised when the cookie signing key cannot be loaded or created."""

    ...
