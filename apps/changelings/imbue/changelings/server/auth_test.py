from pathlib import Path

import pytest

from imbue.changelings.errors import SigningKeyError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CookieSigningKey
from imbue.changelings.primitives import OneTimeCode
from imbue.changelings.server.auth import FileAuthStore


def _make_auth_store(tmp_path: Path) -> FileAuthStore:
    return FileAuthStore(data_directory=tmp_path / "auth")


def test_get_signing_key_generates_key_on_first_access(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    key = store.get_signing_key()
    assert len(str(key)) > 32


def test_get_signing_key_returns_same_key_on_subsequent_access(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    key_first = store.get_signing_key()
    key_second = store.get_signing_key()
    assert key_first == key_second


def test_get_signing_key_persists_across_instances(tmp_path: Path) -> None:
    auth_dir = tmp_path / "auth"
    store_a = FileAuthStore(data_directory=auth_dir)
    key_a = store_a.get_signing_key()

    store_b = FileAuthStore(data_directory=auth_dir)
    key_b = store_b.get_signing_key()

    assert key_a == key_b


def test_get_signing_key_raises_for_empty_key_file(tmp_path: Path) -> None:
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "signing_key").write_text("")

    store = FileAuthStore(data_directory=auth_dir)
    with pytest.raises(SigningKeyError):
        store.get_signing_key()


def test_add_and_validate_one_time_code(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    name = ChangelingName("elena-turing")
    code = OneTimeCode("test-code-82734")

    store.add_one_time_code(changeling_name=name, code=code)

    is_valid = store.validate_and_consume_code(changeling_name=name, code=code)
    assert is_valid is True


def test_validate_rejects_unknown_code(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    name = ChangelingName("elena-turing")

    is_valid = store.validate_and_consume_code(
        changeling_name=name,
        code=OneTimeCode("unknown-code-38294"),
    )
    assert is_valid is False


def test_validate_rejects_already_used_code(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    name = ChangelingName("elena-turing")
    code = OneTimeCode("single-use-code-19283")

    store.add_one_time_code(changeling_name=name, code=code)

    # First use succeeds
    first_result = store.validate_and_consume_code(changeling_name=name, code=code)
    assert first_result is True

    # Second use fails
    second_result = store.validate_and_consume_code(changeling_name=name, code=code)
    assert second_result is False


def test_validate_rejects_code_for_wrong_changeling(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    code = OneTimeCode("shared-code-82734")

    store.add_one_time_code(
        changeling_name=ChangelingName("agent-a"),
        code=code,
    )

    is_valid = store.validate_and_consume_code(
        changeling_name=ChangelingName("agent-b"),
        code=code,
    )
    assert is_valid is False


def test_list_changeling_names_with_valid_codes(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)

    store.add_one_time_code(
        changeling_name=ChangelingName("agent-b"),
        code=OneTimeCode("code-b-38472"),
    )
    store.add_one_time_code(
        changeling_name=ChangelingName("agent-a"),
        code=OneTimeCode("code-a-18293"),
    )

    names = store.list_changeling_names_with_valid_codes()
    assert names == (ChangelingName("agent-a"), ChangelingName("agent-b"))


def test_list_changeling_names_excludes_used_codes(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    name = ChangelingName("agent-a")
    code = OneTimeCode("code-18293")

    store.add_one_time_code(changeling_name=name, code=code)
    store.validate_and_consume_code(changeling_name=name, code=code)

    names = store.list_changeling_names_with_valid_codes()
    assert names == ()


def test_codes_persist_across_store_instances(tmp_path: Path) -> None:
    auth_dir = tmp_path / "auth"
    name = ChangelingName("elena-turing")
    code = OneTimeCode("persistent-code-39271")

    store_a = FileAuthStore(data_directory=auth_dir)
    store_a.add_one_time_code(changeling_name=name, code=code)

    store_b = FileAuthStore(data_directory=auth_dir)
    is_valid = store_b.validate_and_consume_code(changeling_name=name, code=code)
    assert is_valid is True


def test_signing_key_file_has_restricted_permissions(tmp_path: Path) -> None:
    store = _make_auth_store(tmp_path)
    store.get_signing_key()

    key_path = tmp_path / "auth" / "signing_key"
    permissions = key_path.stat().st_mode & 0o777
    assert permissions == 0o600


def test_get_signing_key_reads_existing_key(tmp_path: Path) -> None:
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "signing_key").write_text("my-custom-key-82734")

    store = FileAuthStore(data_directory=auth_dir)
    key = store.get_signing_key()
    assert key == CookieSigningKey("my-custom-key-82734")
