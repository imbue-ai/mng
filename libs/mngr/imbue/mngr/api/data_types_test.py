"""Tests for API data types."""

from pathlib import Path

from imbue.mngr.api.data_types import HostLifecycleOptions
from imbue.mngr.api.data_types import SourceLocation
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import IdleMode


def test_source_location_is_from_agent_true_with_agent_id() -> None:
    """SourceLocation.is_from_agent should be True when agent_id is set."""
    loc = SourceLocation(agent_id=AgentId.generate())
    assert loc.is_from_agent is True


def test_source_location_is_from_agent_true_with_agent_name() -> None:
    """SourceLocation.is_from_agent should be True when agent_name is set."""
    loc = SourceLocation(agent_name=AgentName("test"))
    assert loc.is_from_agent is True


def test_source_location_is_from_agent_false_when_neither() -> None:
    """SourceLocation.is_from_agent should be False when neither ID nor name set."""
    loc = SourceLocation(path=Path("/test"))
    assert loc.is_from_agent is False


def test_source_location_is_from_agent_true_with_both() -> None:
    """SourceLocation.is_from_agent should be True when both ID and name set."""
    loc = SourceLocation(
        agent_id=AgentId.generate(),
        agent_name=AgentName("test"),
    )
    assert loc.is_from_agent is True


# HostLifecycleOptions.to_activity_config tests


def test_host_lifecycle_options_to_activity_config_uses_defaults_when_all_none() -> None:
    """When all options are None, to_activity_config should use all defaults."""
    options = HostLifecycleOptions()
    default_idle_timeout_seconds = 900
    default_idle_mode = IdleMode.AGENT
    default_activity_sources = (ActivitySource.BOOT, ActivitySource.SSH)

    config = options.to_activity_config(
        default_idle_timeout_seconds=default_idle_timeout_seconds,
        default_idle_mode=default_idle_mode,
        default_activity_sources=default_activity_sources,
    )

    assert config.idle_timeout_seconds == default_idle_timeout_seconds
    assert config.idle_mode == default_idle_mode
    assert config.activity_sources == default_activity_sources


def test_host_lifecycle_options_to_activity_config_uses_cli_values_when_provided() -> None:
    """When CLI options are provided, they should override defaults."""
    options = HostLifecycleOptions(
        idle_timeout_seconds=600,
        idle_mode=IdleMode.SSH,
        activity_sources=(ActivitySource.AGENT, ActivitySource.PROCESS),
    )

    config = options.to_activity_config(
        default_idle_timeout_seconds=900,
        default_idle_mode=IdleMode.AGENT,
        default_activity_sources=(ActivitySource.BOOT, ActivitySource.SSH),
    )

    assert config.idle_timeout_seconds == 600
    assert config.idle_mode == IdleMode.SSH
    assert config.activity_sources == (ActivitySource.AGENT, ActivitySource.PROCESS)


def test_host_lifecycle_options_to_activity_config_partial_override() -> None:
    """When only some CLI options are provided, others should use defaults.

    In this test: idle_timeout_seconds is provided (600), but idle_mode and
    activity_sources are None, so they should use the defaults.
    """
    options = HostLifecycleOptions(
        idle_timeout_seconds=600,
        idle_mode=None,
        activity_sources=None,
    )

    config = options.to_activity_config(
        default_idle_timeout_seconds=900,
        default_idle_mode=IdleMode.AGENT,
        default_activity_sources=(ActivitySource.BOOT,),
    )

    # CLI value should be used
    assert config.idle_timeout_seconds == 600
    # Defaults should be used for None values
    assert config.idle_mode == IdleMode.AGENT
    assert config.activity_sources == (ActivitySource.BOOT,)


def test_host_lifecycle_options_to_activity_config_different_partial_override() -> None:
    """Test partial override with different combinations.

    In this test: idle_mode is provided (DISABLED), but idle_timeout_seconds and
    activity_sources are None, so they should use the defaults.
    """
    options = HostLifecycleOptions(
        idle_timeout_seconds=None,
        idle_mode=IdleMode.DISABLED,
        activity_sources=None,
    )

    config = options.to_activity_config(
        default_timeout=3600,
        default_mode=IdleMode.USER,
        default_sources=(ActivitySource.CREATE,),
    )

    # Defaults should be used for None values
    assert config.idle_timeout_seconds == 3600
    # CLI value should be used
    assert config.idle_mode == IdleMode.DISABLED
    # Defaults should be used for None values
    assert config.activity_sources == (ActivitySource.CREATE,)
