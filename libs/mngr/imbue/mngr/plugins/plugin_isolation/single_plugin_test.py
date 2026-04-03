"""Tests with only one plugin enabled -- verifies granular control."""

import pluggy
import pytest

from imbue.mngr.agents.agent_registry import list_registered_agent_types


@pytest.fixture
def enabled_plugins(claude_only_plugins: frozenset[str]) -> frozenset[str]:
    return claude_only_plugins


def test_only_claude_loaded(plugin_manager: pluggy.PluginManager) -> None:
    """Only claude should be registered, not other agent types."""
    registered = list_registered_agent_types()
    assert "claude" in registered
    assert "opencode" not in registered


def test_claude_is_not_blocked(plugin_manager: pluggy.PluginManager) -> None:
    assert not plugin_manager.is_blocked("claude")


def test_opencode_is_blocked(plugin_manager: pluggy.PluginManager) -> None:
    assert plugin_manager.is_blocked("opencode")
