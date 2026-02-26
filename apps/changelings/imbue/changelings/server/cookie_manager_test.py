from inline_snapshot import snapshot

from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CookieSigningKey
from imbue.changelings.server.cookie_manager import create_signed_cookie_value
from imbue.changelings.server.cookie_manager import get_cookie_name_for_changeling
from imbue.changelings.server.cookie_manager import verify_signed_cookie_value


def test_get_cookie_name_for_simple_changeling_name() -> None:
    name = ChangelingName("elena-turing")
    result = get_cookie_name_for_changeling(name)
    assert result == snapshot("changeling_elena-turing")


def test_get_cookie_name_for_name_with_underscores_and_hyphens() -> None:
    name = ChangelingName("my_agent-v2")
    result = get_cookie_name_for_changeling(name)
    assert result == snapshot("changeling_my_agent-v2")


def test_create_and_verify_cookie_round_trip() -> None:
    name = ChangelingName("elena-turing")
    key = CookieSigningKey("test-secret-key-83742")

    cookie_value = create_signed_cookie_value(
        changeling_name=name,
        signing_key=key,
    )
    verified_name = verify_signed_cookie_value(
        cookie_value=cookie_value,
        signing_key=key,
    )

    assert verified_name == name


def test_verify_cookie_returns_none_for_wrong_key() -> None:
    name = ChangelingName("elena-turing")
    correct_key = CookieSigningKey("correct-key-19283")
    wrong_key = CookieSigningKey("wrong-key-84729")

    cookie_value = create_signed_cookie_value(
        changeling_name=name,
        signing_key=correct_key,
    )
    result = verify_signed_cookie_value(
        cookie_value=cookie_value,
        signing_key=wrong_key,
    )

    assert result is None


def test_verify_cookie_returns_none_for_tampered_value() -> None:
    key = CookieSigningKey("test-key-38472")
    result = verify_signed_cookie_value(
        cookie_value="tampered-garbage-value",
        signing_key=key,
    )
    assert result is None


def test_verify_cookie_returns_none_for_empty_value() -> None:
    key = CookieSigningKey("test-key-19384")
    result = verify_signed_cookie_value(
        cookie_value="",
        signing_key=key,
    )
    assert result is None


def test_create_cookie_produces_different_values_for_different_names() -> None:
    key = CookieSigningKey("shared-key-82734")

    value_a = create_signed_cookie_value(
        changeling_name=ChangelingName("agent-a"),
        signing_key=key,
    )
    value_b = create_signed_cookie_value(
        changeling_name=ChangelingName("agent-b"),
        signing_key=key,
    )

    assert value_a != value_b
