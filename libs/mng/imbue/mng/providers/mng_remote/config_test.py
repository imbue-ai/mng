"""Unit tests for mng remote provider config."""

from pydantic import SecretStr

from imbue.mng.primitives import ProviderBackendName
from imbue.mng.providers.mng_remote.config import MngRemoteProviderConfig


def test_mng_remote_config_requires_url_and_token() -> None:
    config = MngRemoteProviderConfig(
        backend=ProviderBackendName("remote"),
        url="https://mng.example.com",
        token=SecretStr("my-secret-token"),
    )
    assert config.url == "https://mng.example.com"
    assert config.token.get_secret_value() == "my-secret-token"
