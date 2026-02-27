from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.primitives import CommandString
from imbue.mng_claude_http.plugin import ClaudeHttpAgentConfig
from imbue.mng_claude_http.plugin import register_agent_type


class TestClaudeHttpAgentConfig:
    def test_default_command(self) -> None:
        config = ClaudeHttpAgentConfig()
        assert config.command == CommandString("python -m imbue.mng_claude_http.cli serve")

    def test_merge_with_override_command(self) -> None:
        base = ClaudeHttpAgentConfig()
        override = ClaudeHttpAgentConfig(command=CommandString("custom-command"))
        merged = base.merge_with(override)
        assert isinstance(merged, ClaudeHttpAgentConfig)
        assert merged.command == CommandString("custom-command")

    def test_merge_with_no_override(self) -> None:
        base = ClaudeHttpAgentConfig()
        override = ClaudeHttpAgentConfig()
        merged = base.merge_with(override)
        assert isinstance(merged, ClaudeHttpAgentConfig)
        assert merged.command == base.command

    def test_merge_with_cli_args(self) -> None:
        base = ClaudeHttpAgentConfig(cli_args=("--port", "8080"))
        override = ClaudeHttpAgentConfig(cli_args=("--work-dir", "/tmp"))
        merged = base.merge_with(override)
        assert isinstance(merged, ClaudeHttpAgentConfig)
        assert merged.cli_args == ("--port", "8080", "--work-dir", "/tmp")

    def test_merge_with_wrong_type_raises(self) -> None:
        base = ClaudeHttpAgentConfig()
        override = AgentTypeConfig()
        try:
            base.merge_with(override)
            assert False, "Should have raised ConfigParseError"
        except Exception as e:
            assert "Cannot merge" in str(e)


class TestRegisterAgentType:
    def test_register_returns_correct_tuple(self) -> None:
        result = register_agent_type()
        assert result[0] == "claude-http"
        assert result[1] is None
        assert result[2] is ClaudeHttpAgentConfig
