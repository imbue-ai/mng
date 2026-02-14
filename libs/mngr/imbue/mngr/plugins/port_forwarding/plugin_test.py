"""Unit tests for the port forwarding plugin module."""

from imbue.mngr.plugins.port_forwarding.plugin import _get_plugin_config_or_none


def test_get_plugin_config_or_none_returns_none() -> None:
    """Test that _get_plugin_config_or_none returns None (not yet wired to config system)."""
    config = _get_plugin_config_or_none()
    assert config is None
