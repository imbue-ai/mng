"""Unit tests for config resolution."""

from pathlib import Path

from pydantic import SecretStr

from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.plugins.port_forwarding.config_resolution import get_plugin_config_from_mngr_config
from imbue.mngr.plugins.port_forwarding.config_resolution import resolve_port_forwarding_config
from imbue.mngr.plugins.port_forwarding.data_types import PLUGIN_NAME
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig
from imbue.mngr.primitives import PluginName


def test_get_plugin_config_returns_none_when_not_configured() -> None:
    config = MngrConfig()
    result = get_plugin_config_from_mngr_config(config)
    assert result is None


def test_get_plugin_config_returns_none_when_disabled() -> None:
    plugin_config = PortForwardingConfig(enabled=False)
    config = MngrConfig(
        plugins={PluginName(PLUGIN_NAME): plugin_config},
    )
    result = get_plugin_config_from_mngr_config(config)
    assert result is None


def test_get_plugin_config_returns_config_when_enabled() -> None:
    plugin_config = PortForwardingConfig(enabled=True)
    config = MngrConfig(
        plugins={PluginName(PLUGIN_NAME): plugin_config},
    )
    result = get_plugin_config_from_mngr_config(config)
    assert result is not None
    assert result.domain_suffix == "mngr.localhost"


def test_resolve_config_auto_generates_tokens(tmp_path: Path) -> None:
    plugin_config = PortForwardingConfig()
    resolved = resolve_port_forwarding_config(plugin_config, config_dir=tmp_path)
    assert resolved.frps_token.get_secret_value() != ""
    assert resolved.auth_token.get_secret_value() != ""


def test_resolve_config_preserves_explicit_tokens(tmp_path: Path) -> None:
    plugin_config = PortForwardingConfig(
        frps_token=SecretStr("explicit-frps"),
        auth_token=SecretStr("explicit-auth"),
    )
    resolved = resolve_port_forwarding_config(plugin_config, config_dir=tmp_path)
    assert resolved.frps_token.get_secret_value() == "explicit-frps"
    assert resolved.auth_token.get_secret_value() == "explicit-auth"


def test_resolve_config_persists_auto_generated_tokens(tmp_path: Path) -> None:
    plugin_config = PortForwardingConfig()
    first = resolve_port_forwarding_config(plugin_config, config_dir=tmp_path)
    second = resolve_port_forwarding_config(plugin_config, config_dir=tmp_path)
    assert first.frps_token.get_secret_value() == second.frps_token.get_secret_value()
    assert first.auth_token.get_secret_value() == second.auth_token.get_secret_value()
