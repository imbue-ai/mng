import pytest

from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.errors import ConfigParseError
from imbue.mng.primitives import CommandString
from imbue.mng_claude_http.plugin import ClaudeHttpAgentConfig
from imbue.mng_claude_http.plugin import register_agent_type


def test_claude_http_config_has_correct_default_command() -> None:
    config = ClaudeHttpAgentConfig()
    assert config.command == CommandString("python -m imbue.mng_claude_http.cli serve")


def test_claude_http_config_merge_with_override_replaces_command() -> None:
    base = ClaudeHttpAgentConfig()
    override = ClaudeHttpAgentConfig(command=CommandString("custom-command"))
    merged = base.merge_with(override)
    assert isinstance(merged, ClaudeHttpAgentConfig)
    assert merged.command == CommandString("custom-command")


def test_claude_http_config_merge_with_no_override_preserves_command() -> None:
    base = ClaudeHttpAgentConfig()
    override = ClaudeHttpAgentConfig()
    merged = base.merge_with(override)
    assert isinstance(merged, ClaudeHttpAgentConfig)
    assert merged.command == base.command


def test_claude_http_config_merge_concatenates_cli_args() -> None:
    base = ClaudeHttpAgentConfig(cli_args=("--port", "8080"))
    override = ClaudeHttpAgentConfig(cli_args=("--work-dir", "/tmp"))
    merged = base.merge_with(override)
    assert isinstance(merged, ClaudeHttpAgentConfig)
    assert merged.cli_args == ("--port", "8080", "--work-dir", "/tmp")


def test_claude_http_config_merge_with_wrong_type_raises_config_parse_error() -> None:
    base = ClaudeHttpAgentConfig()
    override = AgentTypeConfig()
    with pytest.raises(ConfigParseError, match="Cannot merge"):
        base.merge_with(override)


def test_register_agent_type_returns_claude_http_tuple() -> None:
    result = register_agent_type()
    assert result[0] == "claude-http"
    assert result[1] is None
    assert result[2] is ClaudeHttpAgentConfig
