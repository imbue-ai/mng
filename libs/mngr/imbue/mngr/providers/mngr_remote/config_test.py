"""Unit tests for mngr remote provider config."""

from pydantic import SecretStr

from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.providers.mngr_remote.config import MngrRemoteProviderConfig


def test_mngr_remote_config_requires_url_and_token() -> None:
    config = MngrRemoteProviderConfig(
        backend=ProviderBackendName("mngr"),
        url="https://mngr.example.com",
        token=SecretStr("my-secret-token"),
    )
    assert config.url == "https://mngr.example.com"
    assert config.token.get_secret_value() == "my-secret-token"
