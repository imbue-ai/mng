"""Unit tests for the mng_mind provisioning module."""

from pathlib import Path
from typing import Any
from typing import cast

from imbue.mng_llm.data_types import ProvisioningSettings
from imbue.mng_mind.conftest import StubCommandResult
from imbue.mng_mind.conftest import StubHost
from imbue.mng_mind.provisioning import provision_default_content

_DEFAULT_PROVISIONING = ProvisioningSettings()


def test_provision_default_content_writes_global_md() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("GLOBAL.md" in p for p in written_paths)


def test_provision_default_content_writes_thinking_prompt() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("thinking/PROMPT.md" in p for p in written_paths)


def test_provision_default_content_writes_skills_to_thinking() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("thinking/skills/send-message-to-user/SKILL.md" in p for p in written_paths)


def test_provision_default_content_writes_talking_prompt() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("talking/PROMPT.md" in p for p in written_paths)


def test_provision_default_content_writes_working_prompt() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("working/PROMPT.md" in p for p in written_paths)


def test_provision_default_content_writes_verifying_prompt() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("verifying/PROMPT.md" in p for p in written_paths)


def test_provision_default_content_does_not_overwrite_existing() -> None:
    host = StubHost()
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    assert len(host.written_text_files) == 0


def test_provision_default_content_does_not_write_settings_json() -> None:
    """Verify that settings.json is NOT included (it's Claude-specific, handled by mng_claude_mind)."""
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert not any("settings.json" in p for p in written_paths)


def test_provision_default_content_uses_skills_not_dot_claude_skills() -> None:
    """Verify that skills are at thinking/skills/ not thinking/.claude/skills/."""
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_default_content(cast(Any, host), Path("/test/work"), _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert not any(".claude/skills" in p for p in written_paths)
    assert any("thinking/skills/" in p for p in written_paths)
