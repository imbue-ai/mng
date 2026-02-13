"""Unit tests for ttyd data types."""

from imbue.mngr.plugins.ttyd.data_types import DEFAULT_TTYD_BASE_PORT
from imbue.mngr.plugins.ttyd.data_types import TtydConfig
from imbue.mngr.plugins.ttyd.data_types import generate_ttyd_token


def test_ttyd_config_has_defaults() -> None:
    config = TtydConfig()
    assert config.base_port == DEFAULT_TTYD_BASE_PORT
    assert config.enabled is True


def test_generate_ttyd_token_returns_nonempty_string() -> None:
    token = generate_ttyd_token()
    assert isinstance(token, str)
    assert len(token) > 0


def test_generate_ttyd_token_is_unique() -> None:
    tokens = {generate_ttyd_token() for _ in range(10)}
    assert len(tokens) == 10
