"""Unit tests for the test-coder agent type plugin."""

from pathlib import Path
from typing import Any
from typing import cast

import pytest

from imbue.mng.interfaces.data_types import CommandResult
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.primitives import CommandString
from imbue.mng_test_coder.plugin import TestCoderAgent
from imbue.mng_test_coder.plugin import TestCoderConfig
from imbue.mng_test_coder.plugin import _LLM_MATCHED_RESPONSES_LOCAL_CHECKOUT
from imbue.mng_test_coder.plugin import _configure_model_as_default
from imbue.mng_test_coder.plugin import _install_llm_matched_responses_plugin
from imbue.mng_test_coder.plugin import register_agent_type


def test_register_agent_type_returns_correct_tuple() -> None:
    name, agent_class, config_class = register_agent_type()
    assert name == "test-coder"
    assert agent_class is TestCoderAgent
    assert config_class is TestCoderConfig


def test_test_coder_config_defaults() -> None:
    config = TestCoderConfig()
    assert config.install_llm_matched_responses is True
    assert config.install_llm is True
    assert config.trust_working_directory is True


class _StubHost:
    """Simple test double for OnlineHostInterface."""

    def __init__(self, command_results: list[CommandResult] | None = None) -> None:
        self.is_local = True
        self.host_dir = Path("/tmp/mng-test/host")
        self._command_results = command_results or [CommandResult(success=True, stdout="", stderr="")]
        self._call_idx = 0
        self.written_text_files: list[tuple[Path, str]] = []

    def execute_command(self, command: str, **kwargs: Any) -> CommandResult:
        if self._call_idx < len(self._command_results):
            result = self._command_results[self._call_idx]
            self._call_idx += 1
            return result
        return CommandResult(success=True, stdout="", stderr="")

    def write_text_file(self, path: Path, content: str) -> None:
        self.written_text_files.append((path, content))


# --- assemble_command tests ---


def test_assemble_command_returns_idle_loop() -> None:
    """assemble_command should return an idle loop command."""
    agent = TestCoderAgent.__new__(TestCoderAgent)
    host = _StubHost()
    result = agent.assemble_command(host, (), None)
    assert isinstance(result, CommandString)
    assert "sleep 60" in str(result)
    assert "Test agent running" in str(result)


# --- _configure_model_as_default tests ---


def test_configure_model_as_default_writes_toml() -> None:
    """_configure_model_as_default should write changelings.toml with matched-responses."""
    stub = _StubHost()
    work_dir = Path("/work")
    _configure_model_as_default(cast(OnlineHostInterface, stub), work_dir)
    assert len(stub.written_text_files) == 1
    path, content = stub.written_text_files[0]
    assert path == work_dir / "changelings.toml"
    assert "matched-responses" in content


# --- _install_llm_matched_responses_plugin tests ---


def test_install_llm_matched_responses_succeeds_from_pypi() -> None:
    """Plugin install from PyPI should succeed when the command succeeds."""
    host = cast(
        OnlineHostInterface,
        _StubHost(
            command_results=[
                CommandResult(success=True, stdout="", stderr=""),
            ]
        ),
    )
    _install_llm_matched_responses_plugin(host)


@pytest.mark.skipif(
    not _LLM_MATCHED_RESPONSES_LOCAL_CHECKOUT.exists(),
    reason="llm-matched-responses local checkout not available",
)
def test_install_llm_matched_responses_falls_back_to_local() -> None:
    """Should fall back to local checkout when PyPI fails and local checkout exists."""
    host = cast(
        OnlineHostInterface,
        _StubHost(
            command_results=[
                CommandResult(success=False, stdout="", stderr="not found"),
                CommandResult(success=True, stdout="", stderr=""),
            ]
        ),
    )
    _install_llm_matched_responses_plugin(host)
