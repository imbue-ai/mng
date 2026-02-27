from pathlib import Path

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.deployment.local import AgentIdLookupError
from imbue.changelings.deployment.local import MngCreateError
from imbue.changelings.deployment.local import MngNotFoundError
from imbue.changelings.deployment.local import _generate_auth_code
from imbue.changelings.deployment.local import _verify_mng_available
from imbue.changelings.errors import ChangelingError
from imbue.mng.primitives import AgentId


def test_verify_mng_available_succeeds_when_mng_exists() -> None:
    """mng should be available in the test environment (it's a dependency)."""
    _verify_mng_available()


def test_generate_auth_code_creates_login_url(tmp_path: Path) -> None:
    paths = ChangelingPaths(data_dir=tmp_path)
    agent_id = AgentId()

    login_url = _generate_auth_code(
        paths=paths,
        agent_id=agent_id,
        forwarding_server_port=8420,
    )

    assert "http://127.0.0.1:8420/login" in login_url
    assert str(agent_id) in login_url
    assert "one_time_code=" in login_url


def test_generate_auth_code_stores_code_on_disk(tmp_path: Path) -> None:
    paths = ChangelingPaths(data_dir=tmp_path)
    agent_id = AgentId()

    _generate_auth_code(
        paths=paths,
        agent_id=agent_id,
        forwarding_server_port=8420,
    )

    assert paths.auth_dir.exists()
    codes_file = paths.auth_dir / "one_time_codes.json"
    assert codes_file.exists()


def test_mng_not_found_error_is_changeling_error() -> None:
    err = MngNotFoundError("test")
    assert isinstance(err, ChangelingError)


def test_mng_create_error_is_changeling_error() -> None:
    err = MngCreateError("test")
    assert isinstance(err, ChangelingError)


def test_agent_id_lookup_error_is_changeling_error() -> None:
    err = AgentIdLookupError("test")
    assert isinstance(err, ChangelingError)
