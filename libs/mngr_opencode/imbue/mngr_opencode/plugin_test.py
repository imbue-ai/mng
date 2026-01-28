"""Unit tests for OpenCodeAgentConfig."""

from imbue.mngr_opencode.plugin import OpenCodeAgentConfig


# FIXME: This test has been observed to be flaky - it failed once during a test run
# but passed when re-run. Investigate the root cause.
def test_opencode_agent_config_has_correct_defaults() -> None:
    """Verify that OpenCodeAgentConfig has the expected default values."""
    config = OpenCodeAgentConfig()

    assert str(config.command) == "opencode"
    assert config.cli_args == ""
    assert config.permissions == []
    assert config.parent_type is None


def test_opencode_agent_config_merge_with_override() -> None:
    """Verify that merge_with works correctly for OpenCodeAgentConfig."""
    base = OpenCodeAgentConfig()
    override = OpenCodeAgentConfig(cli_args="--verbose")

    merged = base.merge_with(override)

    assert isinstance(merged, OpenCodeAgentConfig)
    assert merged.cli_args == "--verbose"
    assert str(merged.command) == "opencode"
