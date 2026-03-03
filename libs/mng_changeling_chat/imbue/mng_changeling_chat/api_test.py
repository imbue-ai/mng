"""Unit tests for the mng-changeling-chat API module."""

import shlex
from pathlib import Path

from imbue.mng.hosts.host import Host
from imbue.mng_changeling_chat.api import _build_chat_env_vars
from imbue.mng_changeling_chat.api import _build_chat_script_path
from imbue.mng_changeling_chat.api import _build_remote_chat_script
from imbue.mng_changeling_chat.conftest import _TestAgent

# =========================================================================
# Tests for _build_chat_script_path
# =========================================================================


def test_build_chat_script_path() -> None:
    result = _build_chat_script_path(Path("/home/user/.mng"))
    assert result == "/home/user/.mng/commands/chat.sh"


def test_build_chat_script_path_with_different_host_dir() -> None:
    result = _build_chat_script_path(Path("/data/mng"))
    assert result == "/data/mng/commands/chat.sh"


# =========================================================================
# Tests for _build_chat_env_vars
# =========================================================================


def test_build_chat_env_vars(
    local_host_and_agent: tuple[Host, _TestAgent],
) -> None:
    host, agent = local_host_and_agent

    env_vars = _build_chat_env_vars(agent, host)

    assert env_vars["MNG_HOST_DIR"] == str(host.host_dir)
    assert env_vars["MNG_AGENT_STATE_DIR"] == str(host.host_dir / "agents" / str(agent.id))
    assert env_vars["MNG_AGENT_WORK_DIR"] == str(agent.work_dir)
    assert env_vars["MNG_AGENT_ID"] == str(agent.id)
    assert env_vars["MNG_AGENT_NAME"] == str(agent.name)


# =========================================================================
# Tests for _build_remote_chat_script
# =========================================================================


def test_build_remote_chat_script_sets_env_vars(
    local_host_and_agent: tuple[Host, _TestAgent],
) -> None:
    host, agent = local_host_and_agent

    script = _build_remote_chat_script(host.host_dir, agent, host, ["--new"])

    assert f"export MNG_HOST_DIR='{host.host_dir}'" in script
    assert f"export MNG_AGENT_STATE_DIR='{host.host_dir}/agents/{agent.id}'" in script
    assert f"export MNG_AGENT_WORK_DIR='{agent.work_dir}'" in script
    assert f"export MNG_AGENT_ID='{agent.id}'" in script
    assert f"export MNG_AGENT_NAME='{agent.name}'" in script


def test_build_remote_chat_script_execs_chat_sh(
    local_host_and_agent: tuple[Host, _TestAgent],
) -> None:
    host, agent = local_host_and_agent

    script = _build_remote_chat_script(host.host_dir, agent, host, ["--new"])

    assert f"exec '{host.host_dir}/commands/chat.sh' --new" in script


def test_build_remote_chat_script_with_resume_args(
    local_host_and_agent: tuple[Host, _TestAgent],
) -> None:
    host, agent = local_host_and_agent

    script = _build_remote_chat_script(host.host_dir, agent, host, ["--resume", "conv-12345"])

    assert "--resume conv-12345" in script


def test_build_remote_chat_script_quotes_conversation_id_with_special_chars(
    local_host_and_agent: tuple[Host, _TestAgent],
) -> None:
    """Verify that conversation IDs with special characters are safely quoted."""
    host, agent = local_host_and_agent
    dangerous_id = "conv-123; rm -rf /"

    script = _build_remote_chat_script(host.host_dir, agent, host, ["--resume", dangerous_id])

    # The shlex.quote output for the dangerous string should be in the script
    expected_quoted = shlex.quote(dangerous_id)
    assert expected_quoted in script
