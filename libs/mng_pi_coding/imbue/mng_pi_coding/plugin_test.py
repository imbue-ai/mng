"""Unit tests for PiCodingAgentConfig."""

from imbue.mng_pi_coding.plugin import PiCodingAgentConfig


def test_pi_coding_agent_config_has_correct_defaults() -> None:
    """Verify that PiCodingAgentConfig has the expected default values."""
    config = PiCodingAgentConfig()

    assert str(config.command) == "pi"
    assert config.cli_args == ()
    assert config.permissions == []
    assert config.parent_type is None


def test_pi_coding_agent_config_merge_with_override() -> None:
    """Verify that merge_with works correctly for PiCodingAgentConfig."""
    base = PiCodingAgentConfig()
    override = PiCodingAgentConfig(cli_args=("--verbose",))

    merged = base.merge_with(override)

    assert isinstance(merged, PiCodingAgentConfig)
    assert merged.cli_args == ("--verbose",)
    assert str(merged.command) == "pi"
