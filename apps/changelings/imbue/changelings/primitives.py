from imbue.imbue_common.primitives import NonEmptyStr


class ChangelingName(NonEmptyStr):
    """Human-readable name for a changeling agent."""

    ...


class OneTimeCode(NonEmptyStr):
    """A single-use authentication code for changeling access."""

    ...


class CookieSigningKey(NonEmptyStr):
    """Secret key used for signing authentication cookies."""

    ...
