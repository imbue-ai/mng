class ChangelingError(Exception):
    """Base exception for all changelings errors."""

    ...


class SigningKeyError(ChangelingError):
    """Raised when the cookie signing key cannot be loaded or created."""

    ...
