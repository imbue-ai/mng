"""Unit tests for the mng_claude_mind provisioning module."""

from pathlib import Path
from typing import Any
from typing import cast

from imbue.mng.agents.default_plugins.claude_config import encode_claude_project_dir_name
from imbue.mng_claude_mind.conftest import StubCommandResult
from imbue.mng_claude_mind.conftest import StubHost
from imbue.mng_claude_mind.provisioning import _CLAUDE_SETTINGS_JSON
from imbue.mng_claude_mind.provisioning import build_memory_sync_hooks_config
from imbue.mng_claude_mind.provisioning import create_mind_symlinks
from imbue.mng_claude_mind.provisioning import provision_claude_settings
from imbue.mng_claude_mind.provisioning import setup_memory_directory
from imbue.mng_llm.data_types import ProvisioningSettings

_DEFAULT_PROVISIONING = ProvisioningSettings()


# -- provision_claude_settings tests --


def test_provision_claude_settings_writes_when_missing() -> None:
    host = StubHost(command_results={"test -f": StubCommandResult(success=False)})
    provision_claude_settings(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    written_paths = [str(p) for p, _ in host.written_text_files]
    assert any("thinking/.claude/settings.json" in p for p in written_paths)


def test_provision_claude_settings_does_not_overwrite_existing() -> None:
    host = StubHost()
    provision_claude_settings(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    assert len(host.written_text_files) == 0


def test_provision_claude_settings_content() -> None:
    """Verify inlined settings.json has expected permissions."""
    assert "mng *" in _CLAUDE_SETTINGS_JSON
    assert "permissions" in _CLAUDE_SETTINGS_JSON


# -- Memory directory tests --


def test_encode_claude_project_dir_name_replaces_slashes() -> None:
    assert encode_claude_project_dir_name(Path("/home/user/project")) == "-home-user-project"


def test_encode_claude_project_dir_name_replaces_dots() -> None:
    assert encode_claude_project_dir_name(Path("/home/user/.minds/agent")) == "-home-user--minds-agent"


def _run_setup_memory(
    work_dir: str = "/home/user/.minds/agent",
    active_role: str = "thinking",
) -> StubHost:
    """Run setup_memory_directory on a StubHost and return the host for inspection."""
    host = StubHost()
    role_dir_abs = f"{work_dir}/{active_role}"
    setup_memory_directory(cast(Any, host), Path(work_dir), active_role, role_dir_abs, _DEFAULT_PROVISIONING)
    return host


def test_setup_memory_directory_creates_both_dirs() -> None:
    host = _run_setup_memory()
    assert any("mkdir" in c and "/memory" in c for c in host.executed_commands)
    assert any("mkdir" in c and ".claude/projects" in c for c in host.executed_commands)


def test_setup_memory_directory_creates_project_dir_with_home_var() -> None:
    host = _run_setup_memory()
    # Must use $HOME (not ~) so tilde expansion works inside quotes
    mkdir_cmds = [c for c in host.executed_commands if "mkdir" in c and ".claude/projects" in c]
    assert len(mkdir_cmds) >= 1
    assert "$HOME" in mkdir_cmds[0]
    # Project dir name is derived from the work directory (parent of role dir),
    # matching build_memory_sync_hooks_config which uses .parent
    assert "-home-user--minds-agent" in mkdir_cmds[0]


def test_setup_memory_directory_rsyncs_initial_content() -> None:
    host = _run_setup_memory()
    rsync_cmds = [c for c in host.executed_commands if "rsync" in c]
    assert len(rsync_cmds) == 1
    assert "/memory/" in rsync_cmds[0]
    assert "$HOME/.claude/projects/" in rsync_cmds[0]


def test_setup_memory_directory_removes_old_symlink() -> None:
    """Verify that rm -f is used to remove any old symlink before mkdir."""
    host = _run_setup_memory()
    mkdir_cmds = [c for c in host.executed_commands if "rm -f" in c and ".claude/projects" in c]
    assert len(mkdir_cmds) >= 1


def test_setup_memory_directory_does_not_use_literal_tilde() -> None:
    """Verify that ~ is never used in paths (it doesn't expand inside single quotes)."""
    host = _run_setup_memory(work_dir="/home/user/project")
    for cmd in host.executed_commands:
        if ".claude/projects" in cmd:
            assert "~" not in cmd, f"Found literal ~ in command (won't expand in quotes): {cmd}"


def test_build_memory_sync_hooks_config_has_pre_and_post() -> None:
    config = build_memory_sync_hooks_config("/home/user/.minds/agent/thinking")
    assert "PreToolUse" in config["hooks"]
    assert "PostToolUse" in config["hooks"]


def test_build_memory_sync_hooks_config_pre_syncs_role_dir_to_project() -> None:
    """PreToolUse should rsync FROM <role_dir>/memory/ TO Claude project memory/."""
    config = build_memory_sync_hooks_config("/home/user/.minds/agent/thinking")
    pre_cmd = config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    # rsync source comes before destination: rsync -a --delete SRC/ DST/
    role_dir_pos = pre_cmd.index("/home/user/.minds/agent/thinking/memory")
    project_pos = pre_cmd.index("$HOME/.claude/projects/")
    assert role_dir_pos < project_pos, "PreToolUse should sync role_dir -> project (role_dir first in rsync args)"


def test_build_memory_sync_hooks_config_post_syncs_project_to_role_dir() -> None:
    """PostToolUse should rsync FROM Claude project memory/ TO <role_dir>/memory/."""
    config = build_memory_sync_hooks_config("/home/user/.minds/agent/thinking")
    post_cmd = config["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    # rsync source comes before destination: rsync -a --delete SRC/ DST/
    role_dir_pos = post_cmd.index("/home/user/.minds/agent/thinking/memory")
    project_pos = post_cmd.index("$HOME/.claude/projects/")
    assert project_pos < role_dir_pos, "PostToolUse should sync project -> role_dir (project first in rsync args)"


# -- Symlink tests --


def test_create_mind_symlinks_checks_global_md() -> None:
    host = StubHost()
    create_mind_symlinks(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    assert any("GLOBAL.md" in c for c in host.executed_commands)


def test_create_mind_symlinks_checks_thinking_prompt() -> None:
    host = StubHost()
    create_mind_symlinks(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    assert any("thinking/PROMPT.md" in c for c in host.executed_commands)


def test_create_mind_symlinks_creates_claude_md() -> None:
    host = StubHost()
    create_mind_symlinks(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    assert any("ln -sf" in c and "CLAUDE.md" in c for c in host.executed_commands)


def test_create_mind_symlinks_creates_claude_local_md() -> None:
    host = StubHost()
    create_mind_symlinks(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    assert any("ln -sf" in c and "CLAUDE.local.md" in c for c in host.executed_commands)


def test_create_mind_symlinks_creates_skills_symlink() -> None:
    """Verify that .claude/skills is symlinked to skills."""
    host = StubHost()
    create_mind_symlinks(cast(Any, host), Path("/test/work"), "thinking", _DEFAULT_PROVISIONING)

    assert any("ln -sf" in c and ".claude/skills" in c for c in host.executed_commands)
    assert any("thinking/skills" in c for c in host.executed_commands)
