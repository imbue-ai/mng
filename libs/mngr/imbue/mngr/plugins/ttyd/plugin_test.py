"""Unit tests for the ttyd plugin module."""

from pathlib import Path

import pluggy

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.model_update import to_update
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.conftest import create_test_base_agent
from imbue.mngr.conftest import make_mngr_ctx
from imbue.mngr.plugins.ttyd.data_types import PLUGIN_NAME
from imbue.mngr.plugins.ttyd.data_types import TtydConfig
from imbue.mngr.plugins.ttyd.plugin import _allocate_port
from imbue.mngr.plugins.ttyd.plugin import _get_ttyd_config
from imbue.mngr.plugins.ttyd.plugin import on_agent_created
from imbue.mngr.plugins.ttyd.plugin import on_agent_destroyed
from imbue.mngr.primitives import PluginName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.local.instance import LocalProviderInstance


def test_get_ttyd_config_returns_default_when_not_configured(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _get_ttyd_config returns default TtydConfig when no plugin config exists."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    config = _get_ttyd_config(agent)
    assert config is not None
    assert isinstance(config, TtydConfig)


def test_get_ttyd_config_returns_none_when_disabled(
    temp_config: MngrConfig,
    temp_profile_dir: Path,
    temp_host_dir: Path,
    temp_work_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test that _get_ttyd_config returns None when the plugin is disabled."""
    # Build a config with ttyd disabled
    disabled_config = TtydConfig(enabled=False)
    updated_plugins = dict(temp_config.plugins)
    updated_plugins[PluginName(PLUGIN_NAME)] = disabled_config
    config_with_disabled_ttyd = temp_config.model_copy_update(
        to_update(temp_config.field_ref().plugins, updated_plugins),
    )

    cg = ConcurrencyGroup(name="test")
    with cg:
        ctx = make_mngr_ctx(config_with_disabled_ttyd, plugin_manager, temp_profile_dir, concurrency_group=cg)
        provider = LocalProviderInstance(
            name=ProviderInstanceName("local"),
            host_dir=temp_host_dir,
            mngr_ctx=ctx,
        )
        agent = create_test_base_agent(provider, temp_host_dir, temp_work_dir)

        config = _get_ttyd_config(agent)
        assert config is None


def test_allocate_port_returns_deterministic_port(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that _allocate_port returns a consistent port for the same agent."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    config = TtydConfig()

    port1 = _allocate_port(agent, config)
    port2 = _allocate_port(agent, config)

    assert port1 == port2
    assert port1 >= int(config.base_port)
    assert port1 < int(config.base_port) + 1000


def test_allocate_port_differs_for_different_agents(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that different agents get different ports (with high probability)."""
    agent1 = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    agent2 = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    config = TtydConfig()

    port1 = _allocate_port(agent1, config)
    port2 = _allocate_port(agent2, config)

    # Different agent IDs should produce different ports (extremely unlikely to collide)
    assert port1 != port2


def test_on_agent_created_stores_plugin_data(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that on_agent_created stores the port and token in plugin data."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    host = agent.get_host()

    # Call the hook directly -- ttyd/forward-service won't be installed locally,
    # but the plugin data should still be written before those commands run
    on_agent_created(agent=agent, host=host)

    plugin_data = agent.get_plugin_data(PLUGIN_NAME)
    assert "ttyd_port" in plugin_data
    assert "ttyd_token" in plugin_data
    assert isinstance(plugin_data["ttyd_port"], int)
    assert isinstance(plugin_data["ttyd_token"], str)
    assert len(plugin_data["ttyd_token"]) > 0


def test_on_agent_destroyed_is_noop_without_plugin_data(
    local_provider: LocalProviderInstance,
    temp_host_dir: Path,
    temp_work_dir: Path,
) -> None:
    """Test that on_agent_destroyed does nothing when no plugin data exists."""
    agent = create_test_base_agent(local_provider, temp_host_dir, temp_work_dir)
    host = agent.get_host()

    # Should not raise -- gracefully handles missing plugin data
    on_agent_destroyed(agent=agent, host=host)
