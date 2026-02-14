"""Unit tests for api_server data types."""

from imbue.mngr.plugins.api_server.data_types import ApiServerConfig
from imbue.mngr.plugins.api_server.data_types import DEFAULT_API_PORT


def test_api_server_config_has_defaults() -> None:
    config = ApiServerConfig()
    assert config.port == DEFAULT_API_PORT
    assert config.host == "0.0.0.0"
    assert config.api_token is None
    assert config.enabled is True
