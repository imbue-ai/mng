"""Unit tests for api_server data types."""

from imbue.mngr.plugins.api_server.data_types import ApiServerConfig
from imbue.mngr.plugins.api_server.data_types import DEFAULT_API_PORT
from imbue.mngr.plugins.api_server.data_types import generate_api_token


def test_api_server_config_has_defaults() -> None:
    config = ApiServerConfig()
    assert config.port == DEFAULT_API_PORT
    assert config.host == "0.0.0.0"
    assert config.api_token is None
    assert config.enabled is True


def test_generate_api_token_is_nonempty() -> None:
    token = generate_api_token()
    assert isinstance(token, str)
    assert len(token) > 0


def test_generate_api_token_is_unique() -> None:
    tokens = {generate_api_token() for _ in range(10)}
    assert len(tokens) == 10
