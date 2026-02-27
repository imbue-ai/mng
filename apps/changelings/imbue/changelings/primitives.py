from pydantic import SecretStr

from imbue.imbue_common.primitives import NonEmptyStr


class OneTimeCode(NonEmptyStr):
    """A single-use authentication code for changeling access."""

    ...


class CookieSigningKey(SecretStr):
    """Secret key used for signing authentication cookies."""

    ...
