import re
from typing import Final

from itsdangerous import BadSignature
from itsdangerous import URLSafeTimedSerializer

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CookieSigningKey
from imbue.imbue_common.pure import pure

_COOKIE_SALT: Final[str] = "changeling-auth"

_COOKIE_PREFIX: Final[str] = "changeling_"

_COOKIE_MAX_AGE_SECONDS: Final[int] = 30 * 24 * 60 * 60

# Only allow alphanumeric characters, hyphens, and underscores in cookie names
_SAFE_COOKIE_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-zA-Z0-9_-]")


@pure
def get_cookie_name_for_changeling(changeling_name: ChangelingName) -> str:
    """Return the cookie name used to store auth for a specific changeling."""
    sanitized = _SAFE_COOKIE_NAME_PATTERN.sub("_", str(changeling_name))
    return f"{_COOKIE_PREFIX}{sanitized}"


def create_signed_cookie_value(
    changeling_name: ChangelingName,
    signing_key: CookieSigningKey,
) -> str:
    """Create a signed cookie value containing the changeling name."""
    serializer = URLSafeTimedSerializer(secret_key=str(signing_key))
    return serializer.dumps(str(changeling_name), salt=_COOKIE_SALT)


def verify_signed_cookie_value(
    cookie_value: str,
    signing_key: CookieSigningKey,
) -> ChangelingName | None:
    """Verify and decode a signed cookie, returning the changeling name or None if invalid."""
    serializer = URLSafeTimedSerializer(secret_key=str(signing_key))
    try:
        name = serializer.loads(
            cookie_value,
            salt=_COOKIE_SALT,
            max_age=_COOKIE_MAX_AGE_SECONDS,
        )
    except BadSignature:
        return None
    if not isinstance(name, str) or not name:
        return None
    return ChangelingName(name)
