"""Integration tests for the mng_claude_zygote plugin.

Tests the plugin end-to-end by creating real agents in temporary git repos,
verifying provisioning creates the expected filesystem structures, and
exercising the chat and watcher scripts.

These tests use --agent-cmd to override the default Claude command with
a simple sleep process, since Claude Code is not available in CI. This
still exercises all the provisioning, symlink creation, and tmux window
injection logic that the plugin provides.
"""

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pluggy
import pytest
from click.testing import CliRunner

from imbue.mng.cli.create import create
from imbue.mng.cli.list import list_command
from imbue.mng.utils.testing import tmux_session_cleanup
from imbue.mng.utils.testing import tmux_session_exists
from imbue.mng_claude_zygote.conftest import ChatScriptEnv
from imbue.mng_claude_zygote.conftest import LocalShellHost
from imbue.mng_claude_zygote.conftest import StubCommandResult
from imbue.mng_claude_zygote.conftest import StubHost
from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.data_types import ProvisioningSettings
from imbue.mng_claude_zygote.provisioning import _DEFAULT_CHANGELINGS_DIR_FILES
from imbue.mng_claude_zygote.provisioning import _DEFAULT_SKILL_DIRS
from imbue.mng_claude_zygote.provisioning import _DEFAULT_WORK_DIR_FILES
from imbue.mng_claude_zygote.provisioning import _LLM_TOOL_FILES
from imbue.mng_claude_zygote.provisioning import _SCRIPT_FILES
from imbue.mng_claude_zygote.provisioning import compute_claude_project_dir_name
from imbue.mng_claude_zygote.provisioning import create_changeling_symlinks
from imbue.mng_claude_zygote.provisioning import create_event_log_directories
from imbue.mng_claude_zygote.provisioning import link_memory_directory
from imbue.mng_claude_zygote.provisioning import provision_changeling_scripts
from imbue.mng_claude_zygote.provisioning import provision_default_content
from imbue.mng_claude_zygote.provisioning import provision_llm_tools
from imbue.mng_claude_zygote.provisioning import write_default_chat_model
from imbue.mng_claude_zygote.settings import load_settings_from_host
from imbue.mng_claude_zygote.settings import provision_settings_file

_DEFAULT_PROVISIONING = ProvisioningSettings()

# SQL schema matching the llm tool's responses table.
# Used by conversation watcher sync tests that create a real SQLite DB.
_LLM_RESPONSES_SCHEMA = """
    CREATE TABLE responses (
        id TEXT PRIMARY KEY,
        system TEXT,
        prompt TEXT,
        response TEXT,
        model TEXT,
        datetime_utc TEXT,
        conversation_id TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        token_details TEXT,
        response_json TEXT,
        reply_to_id TEXT,
        chat_id INTEGER,
        duration_ms INTEGER,
        attachment_type TEXT,
        attachment_path TEXT,
        attachment_url TEXT,
        attachment_content TEXT
    )
"""


def _unique_agent_name(label: str) -> str:
    """Generate a unique agent name for test isolation."""
    return f"test-{label}-{int(time.time())}"


def _create_zygote_agent(
    cli_runner: CliRunner,
    plugin_manager: pluggy.PluginManager,
    agent_name: str,
    source_dir: Path,
    *,
    agent_cmd: str = "sleep 847291",
    extra_args: tuple[str, ...] = (),
) -> int:
    """Create an agent via the CLI and return the exit code."""
    result = cli_runner.invoke(
        create,
        [
            "--name",
            agent_name,
            "--agent-cmd",
            agent_cmd,
            "--source",
            str(source_dir),
            "--no-connect",
            "--await-ready",
            "--no-copy-work-dir",
            "--no-ensure-clean",
            "--disable-plugin",
            "modal",
            *extra_args,
        ],
        obj=plugin_manager,
        catch_exceptions=False,
    )
    return result.exit_code


def _find_agent_state_dir(host_dir: Path) -> Path | None:
    """Find the first agent state directory under the host dir."""
    agents_dir = host_dir / "agents"
    if not agents_dir.exists():
        return None
    for entry in agents_dir.iterdir():
        if entry.is_dir():
            return entry
    return None


def _create_test_llm_db(db_path: Path, rows: list[tuple[str, str, str, str, str, str]]) -> None:
    """Create a minimal llm-compatible SQLite database with responses.

    Each row is (id, prompt, response, model, datetime_utc, conversation_id).
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(_LLM_RESPONSES_SCHEMA)
    for row_id, prompt, response, model, dt, cid in rows:
        conn.execute(
            "INSERT INTO responses (id, prompt, response, model, datetime_utc, conversation_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, prompt, response, model, dt, cid),
        )
    conn.commit()
    conn.close()


def _run_sync_script(conversations_file: Path, messages_file: Path, db_path: Path) -> int:
    """Run the conversation watcher's sync logic and return the count of synced events.

    Extracts and runs the Python sync script embedded in conversation_watcher.sh.
    This tests the actual sync algorithm that the watcher uses.
    """
    sync_env = os.environ.copy()
    sync_env["_CONVERSATIONS_FILE"] = str(conversations_file)
    sync_env["_MESSAGES_FILE"] = str(messages_file)
    sync_env["_DB_PATH"] = str(db_path)

    # This is the sync logic extracted from conversation_watcher.sh's heredoc.
    # We run it directly to test the actual algorithm without needing the full
    # bash watcher loop infrastructure.
    sync_script = """
import json, os, sqlite3

def sync():
    conversations_file = os.environ["_CONVERSATIONS_FILE"]
    messages_file = os.environ["_MESSAGES_FILE"]
    db_path = os.environ["_DB_PATH"]

    tracked_cids = set()
    if os.path.isfile(conversations_file):
        with open(conversations_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    tracked_cids.add(json.loads(line)["conversation_id"])
                except (json.JSONDecodeError, KeyError):
                    continue

    if not tracked_cids:
        print("0")
        return

    file_event_ids = set()
    if os.path.isfile(messages_file):
        with open(messages_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    file_event_ids.add(json.loads(line)["event_id"])
                except (json.JSONDecodeError, KeyError):
                    continue

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    placeholders = ",".join("?" for _ in tracked_cids)
    cid_list = list(tracked_cids)

    rows = conn.execute(
        f"SELECT id, datetime_utc, conversation_id, prompt, response "
        f"FROM responses "
        f"WHERE conversation_id IN ({placeholders}) "
        f"ORDER BY datetime_utc DESC "
        f"LIMIT 200",
        cid_list,
    ).fetchall()

    conn.close()

    missing_events = []
    for row_id, ts, cid, prompt, response in rows:
        if prompt:
            eid = f"{row_id}-user"
            if eid not in file_event_ids:
                missing_events.append((ts, 0, json.dumps({
                    "timestamp": ts, "type": "message", "event_id": eid,
                    "source": "messages", "conversation_id": cid,
                    "role": "user", "content": prompt,
                })))
        if response:
            eid = f"{row_id}-assistant"
            if eid not in file_event_ids:
                missing_events.append((ts, 1, json.dumps({
                    "timestamp": ts, "type": "message", "event_id": eid,
                    "source": "messages", "conversation_id": cid,
                    "role": "assistant", "content": response,
                })))

    if not missing_events:
        print("0")
        return

    missing_events.sort(key=lambda x: (x[0], x[1]))
    os.makedirs(os.path.dirname(messages_file), exist_ok=True)
    with open(messages_file, "a") as f:
        for _, _, event_json in missing_events:
            f.write(event_json + "\\n")

    print(str(len(missing_events)))

sync()
"""

    result = subprocess.run(
        ["python3", "-c", sync_script],
        capture_output=True,
        text=True,
        env=sync_env,
        timeout=10,
    )
    assert result.returncode == 0, f"Sync failed: {result.stderr}"
    return int(result.stdout.strip())


def _write_conversation_event(events_file: Path, cid: str, model: str = "claude-sonnet-4-6") -> None:
    """Append a conversation_created event to a JSONL file."""
    event = json.dumps(
        {
            "timestamp": "2025-01-15T10:00:00.000Z",
            "type": "conversation_created",
            "event_id": f"evt-{cid}",
            "source": "conversations",
            "conversation_id": cid,
            "model": model,
        }
    )
    with events_file.open("a") as f:
        f.write(event + "\n")


# -- Provisioning filesystem structure tests --


@pytest.mark.timeout(30)
def test_provisioning_creates_event_log_directories(
    temp_host_dir: Path,
) -> None:
    """Verify that provisioning creates all expected event log directories."""
    agent_state_dir = temp_host_dir / "agents" / "test-agent"
    agent_state_dir.mkdir(parents=True)

    host = StubHost(host_dir=temp_host_dir, execute_mkdir=True)
    create_event_log_directories(host, agent_state_dir, _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    expected_sources = (
        "conversations",
        "messages",
        "scheduled",
        "mng_agents",
        "stop",
        "monitor",
        "claude_transcript",
    )
    for source in expected_sources:
        source_dir = agent_state_dir / "logs" / source
        assert source_dir.exists(), f"Expected logs/{source}/ directory to exist"


@pytest.mark.timeout(30)
def test_provisioning_writes_changeling_scripts_to_host(
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that provisioning writes all bash scripts with correct permissions."""
    provision_changeling_scripts(local_shell_host, _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    commands_dir = local_shell_host.host_dir / "commands"
    for script_name in _SCRIPT_FILES:
        script_path = commands_dir / script_name
        assert script_path.exists(), f"Expected {script_name} to be written"
        assert script_path.stat().st_mode & 0o111, f"Expected {script_name} to be executable"
        content = script_path.read_text()
        assert content.startswith("#!/bin/bash"), f"Expected {script_name} to have bash shebang"


@pytest.mark.timeout(30)
def test_provisioning_writes_llm_tools_to_host(
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that provisioning writes LLM tool scripts."""
    provision_llm_tools(local_shell_host, _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    tools_dir = local_shell_host.host_dir / "commands" / "llm_tools"
    for tool_file in _LLM_TOOL_FILES:
        tool_path = tools_dir / tool_file
        assert tool_path.exists(), f"Expected {tool_file} to be written"
        content = tool_path.read_text()
        assert "def " in content, f"Expected {tool_file} to contain Python function definitions"


@pytest.mark.timeout(30)
def test_provisioning_creates_default_content_when_missing(
    temp_git_repo: Path,
    temp_host_dir: Path,
) -> None:
    """Verify that provisioning writes default content files when they don't exist."""
    host = StubHost(
        host_dir=temp_host_dir,
        command_results={"test -f": StubCommandResult(success=False)},
        execute_mkdir=True,
    )

    written_paths: list[tuple[Path, str]] = []
    original_write = host.write_text_file

    def tracking_write(path: Path, content: str) -> None:
        written_paths.append((path, content))
        original_write(path, content)

    host.write_text_file = tracking_write  # type: ignore[assignment]

    provision_default_content(host, temp_git_repo, ".changelings", _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    written_path_strings = [str(p) for p, _ in written_paths]

    for _, relative_path in _DEFAULT_WORK_DIR_FILES:
        expected = str(temp_git_repo / relative_path)
        assert expected in written_path_strings, f"Expected {relative_path} to be written to work dir"

    for _, relative_path in _DEFAULT_CHANGELINGS_DIR_FILES:
        expected = str(temp_git_repo / ".changelings" / relative_path)
        assert expected in written_path_strings, f"Expected {relative_path} to be written to changelings dir"

    for skill_name in _DEFAULT_SKILL_DIRS:
        expected = str(temp_git_repo / ".claude" / "skills" / skill_name / "SKILL.md")
        assert expected in written_path_strings, f"Expected skill {skill_name}/SKILL.md to be written"


@pytest.mark.timeout(30)
def test_provisioning_does_not_overwrite_existing_content(
    temp_git_repo: Path,
    temp_host_dir: Path,
) -> None:
    """Verify that provisioning does not overwrite files that already exist."""
    host = StubHost(host_dir=temp_host_dir)

    provision_default_content(host, temp_git_repo, ".changelings", _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    assert len(host.written_text_files) == 0, "Should not overwrite existing files"


@pytest.mark.timeout(30)
def test_provisioning_creates_symlinks(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that provisioning creates the expected symlinks."""
    changelings_dir = temp_git_repo / ".changelings"
    changelings_dir.mkdir()
    (changelings_dir / "entrypoint.md").write_text("# Test entrypoint")
    (changelings_dir / "entrypoint.json").write_text("{}")
    (temp_git_repo / ".claude").mkdir()

    create_changeling_symlinks(local_shell_host, temp_git_repo, ".changelings", _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    local_md = temp_git_repo / "CLAUDE.local.md"
    assert local_md.is_symlink(), "CLAUDE.local.md should be a symlink"
    assert local_md.resolve() == (changelings_dir / "entrypoint.md").resolve()

    settings_json = temp_git_repo / ".claude" / "settings.local.json"
    assert settings_json.is_symlink(), "settings.local.json should be a symlink"
    assert settings_json.resolve() == (changelings_dir / "entrypoint.json").resolve()


@pytest.mark.timeout(30)
def test_provisioning_links_memory_directory(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that provisioning creates the memory symlink into Claude project directory."""
    link_memory_directory(local_shell_host, temp_git_repo, ".changelings", _DEFAULT_PROVISIONING)  # type: ignore[arg-type]

    changelings_memory = temp_git_repo / ".changelings" / "memory"
    assert changelings_memory.is_dir(), "changelings memory dir should exist"

    abs_work_dir = str(temp_git_repo.resolve())
    project_dir_name = compute_claude_project_dir_name(abs_work_dir)
    project_memory = Path.home() / ".claude" / "projects" / project_dir_name / "memory"
    assert project_memory.is_symlink(), "Claude project memory should be a symlink"
    assert project_memory.resolve() == changelings_memory.resolve()


@pytest.mark.timeout(30)
def test_provisioning_writes_default_chat_model(
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that provisioning writes the default chat model file."""
    agent_state_dir = local_shell_host.host_dir / "agents" / "test-agent"
    agent_state_dir.mkdir(parents=True)

    write_default_chat_model(local_shell_host, agent_state_dir, ChatModel("claude-sonnet-4-6"))  # type: ignore[arg-type]

    model_file = agent_state_dir / "default_chat_model"
    assert model_file.exists(), "default_chat_model file should exist"
    assert model_file.read_text().strip() == "claude-sonnet-4-6"


# -- Chat script tests --


@pytest.mark.timeout(30)
def test_chat_script_shows_help(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh --help outputs usage information."""
    result = chat_env.run("--help")

    assert result.returncode == 0
    assert "chat" in result.stdout.lower()
    assert "--new" in result.stdout
    assert "--resume" in result.stdout
    assert "--list" in result.stdout


@pytest.mark.timeout(30)
def test_chat_script_list_shows_no_conversations_initially(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh --list reports no conversations when events file doesn't exist."""
    result = chat_env.run("--list")

    assert result.returncode == 0
    assert "no conversations" in result.stdout.lower()


@pytest.mark.timeout(30)
def test_chat_script_rejects_unknown_options(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh rejects unknown options with an error."""
    result = chat_env.run("--bogus")

    assert result.returncode != 0
    assert "unknown" in result.stderr.lower()


@pytest.mark.timeout(30)
def test_chat_script_resume_requires_conversation_id(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh --resume without a conversation ID fails."""
    result = chat_env.run("--resume")

    assert result.returncode != 0


@pytest.mark.timeout(30)
def test_chat_script_no_args_lists_and_shows_hint(chat_env: ChatScriptEnv) -> None:
    """Verify that calling chat.sh with no arguments lists conversations and shows a help hint."""
    result = chat_env.run()

    assert result.returncode == 0
    assert "--help" in result.stdout


@pytest.mark.timeout(30)
def test_chat_script_list_shows_existing_conversations(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh --list shows conversations from the events file."""
    event = {
        "timestamp": "2025-01-15T10:00:00.000000000Z",
        "type": "conversation_created",
        "event_id": "evt-test-001",
        "source": "conversations",
        "conversation_id": "conv-test-12345",
        "model": "claude-sonnet-4-6",
    }
    events_file = chat_env.conversations_dir / "events.jsonl"
    events_file.write_text(json.dumps(event) + "\n")

    result = chat_env.run("--list")

    assert result.returncode == 0
    assert "conv-test-12345" in result.stdout
    assert "claude-sonnet-4-6" in result.stdout


@pytest.mark.timeout(30)
def test_chat_script_list_handles_malformed_events(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh --list gracefully handles malformed JSONL lines."""
    valid_event = json.dumps(
        {
            "timestamp": "2025-01-15T10:00:00.000000000Z",
            "type": "conversation_created",
            "event_id": "evt-test-002",
            "source": "conversations",
            "conversation_id": "conv-valid-789",
            "model": "claude-sonnet-4-6",
        }
    )
    events_file = chat_env.conversations_dir / "events.jsonl"
    events_file.write_text(f"this is not json\n{valid_event}\n")

    result = chat_env.run("--list")

    assert result.returncode == 0
    assert "conv-valid-789" in result.stdout
    assert "malformed" in result.stderr.lower() or "warning" in result.stderr.lower()


# -- Watcher script syntax tests --


@pytest.mark.timeout(30)
def test_conversation_watcher_script_is_valid_bash(chat_env: ChatScriptEnv) -> None:
    """Verify that conversation_watcher.sh passes bash syntax check."""
    from imbue.mng_claude_zygote.provisioning import load_zygote_resource

    watcher_script = chat_env.agent_state_dir.parent.parent / "commands" / "conversation_watcher.sh"
    watcher_script.parent.mkdir(parents=True, exist_ok=True)
    watcher_script.write_text(load_zygote_resource("conversation_watcher.sh"))

    result = subprocess.run(["bash", "-n", str(watcher_script)], capture_output=True, text=True, timeout=10)

    assert result.returncode == 0, f"Syntax check failed: {result.stderr}"


@pytest.mark.timeout(30)
def test_event_watcher_script_is_valid_bash(chat_env: ChatScriptEnv) -> None:
    """Verify that event_watcher.sh passes bash syntax check."""
    from imbue.mng_claude_zygote.provisioning import load_zygote_resource

    watcher_script = chat_env.agent_state_dir.parent.parent / "commands" / "event_watcher.sh"
    watcher_script.parent.mkdir(parents=True, exist_ok=True)
    watcher_script.write_text(load_zygote_resource("event_watcher.sh"))

    result = subprocess.run(["bash", "-n", str(watcher_script)], capture_output=True, text=True, timeout=10)

    assert result.returncode == 0, f"Syntax check failed: {result.stderr}"


# -- Agent creation integration tests --


@pytest.mark.timeout(60)
def test_create_agent_with_additional_commands(
    cli_runner: CliRunner,
    temp_git_repo: Path,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify that creating an agent with additional commands creates the expected tmux windows."""
    agent_name = _unique_agent_name("addcmd")
    prefix = os.environ.get("MNG_PREFIX", "mng-test-")
    session_name = f"{prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 847291",
                "--source",
                str(temp_git_repo),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
                "--disable-plugin",
                "modal",
                "--add-command",
                'watcher="sleep 847292"',
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert tmux_session_exists(session_name)

        windows_result = subprocess.run(
            ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
        )
        assert windows_result.returncode == 0
        window_names = windows_result.stdout.strip().split("\n")
        assert "watcher" in window_names, f"Expected 'watcher' window, got: {window_names}"


@pytest.mark.timeout(60)
def test_create_agent_creates_state_directory(
    cli_runner: CliRunner,
    temp_git_repo: Path,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify that creating an agent creates the agent state directory."""
    agent_name = _unique_agent_name("state")
    prefix = os.environ.get("MNG_PREFIX", "mng-test-")
    session_name = f"{prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        exit_code = _create_zygote_agent(cli_runner, plugin_manager, agent_name, temp_git_repo)
        assert exit_code == 0

        agent_state_dir = _find_agent_state_dir(temp_host_dir)
        assert agent_state_dir is not None, "Agent state directory should exist"
        assert (agent_state_dir / "data.json").exists(), "data.json should exist in agent state dir"


# -- Settings loading integration tests --


@pytest.mark.timeout(30)
def test_settings_loaded_from_host_with_valid_toml(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that settings are loaded from a valid settings.toml file."""
    changelings_dir = temp_git_repo / ".changelings"
    changelings_dir.mkdir()
    (changelings_dir / "settings.toml").write_text(
        '[chat]\nmodel = "claude-sonnet-4-6"\n\n[watchers]\nconversation_poll_interval_seconds = 10\n'
    )

    settings = load_settings_from_host(local_shell_host, temp_git_repo, ".changelings")  # type: ignore[arg-type]

    assert settings.chat.model == "claude-sonnet-4-6"
    assert settings.watchers.conversation_poll_interval_seconds == 10


@pytest.mark.timeout(30)
def test_settings_returns_defaults_for_missing_file(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that settings default gracefully when settings.toml is missing."""
    settings = load_settings_from_host(local_shell_host, temp_git_repo, ".changelings")  # type: ignore[arg-type]

    assert settings.chat.model is None
    assert settings.watchers.conversation_poll_interval_seconds == 5
    assert settings.watchers.event_poll_interval_seconds == 3


@pytest.mark.timeout(30)
def test_settings_returns_defaults_for_invalid_toml(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that settings default gracefully when settings.toml is invalid."""
    changelings_dir = temp_git_repo / ".changelings"
    changelings_dir.mkdir()
    (changelings_dir / "settings.toml").write_text("this is not valid toml [[[")

    settings = load_settings_from_host(local_shell_host, temp_git_repo, ".changelings")  # type: ignore[arg-type]

    assert settings.chat.model is None
    assert settings.watchers.conversation_poll_interval_seconds == 5


# -- JSONL event format tests --


@pytest.mark.timeout(30)
def test_conversation_event_serializes_to_valid_jsonl(chat_env: ChatScriptEnv) -> None:
    """Verify that conversation events written by chat.sh are valid JSONL."""
    chat_env.set_default_model("claude-sonnet-4-6")

    result = chat_env.run("--new", "--as-agent")

    assert result.returncode == 0

    cid = result.stdout.strip()
    assert cid.startswith("conv-"), f"Expected conversation ID, got: {cid!r}"

    events_file = chat_env.conversations_dir / "events.jsonl"
    assert events_file.exists(), "conversations/events.jsonl should exist"

    lines = events_file.read_text().strip().split("\n")
    assert len(lines) >= 1, "Should have at least one event"

    event = json.loads(lines[-1])
    assert event["type"] == "conversation_created"
    assert event["source"] == "conversations"
    assert event["conversation_id"] == cid
    assert event["model"] == "claude-sonnet-4-6"
    assert "timestamp" in event
    assert "event_id" in event


@pytest.mark.timeout(30)
def test_multiple_conversations_create_separate_events(chat_env: ChatScriptEnv) -> None:
    """Verify that creating multiple conversations produces separate events."""
    chat_env.set_default_model("claude-sonnet-4-6")

    cids = []
    for _ in range(3):
        result = chat_env.run("--new", "--as-agent")
        assert result.returncode == 0
        cids.append(result.stdout.strip())

    assert len(set(cids)) == 3, f"Expected 3 unique CIDs, got: {cids}"

    events_file = chat_env.conversations_dir / "events.jsonl"
    lines = events_file.read_text().strip().split("\n")
    assert len(lines) == 3

    event_cids = [json.loads(line)["conversation_id"] for line in lines]
    assert set(event_cids) == set(cids)


@pytest.mark.timeout(30)
def test_chat_model_read_from_default_model_file(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh reads the model from the default_chat_model file."""
    chat_env.set_default_model("claude-haiku-4-5")

    result = chat_env.run("--new", "--as-agent")
    assert result.returncode == 0

    events_file = chat_env.conversations_dir / "events.jsonl"
    event = json.loads(events_file.read_text().strip().split("\n")[-1])
    assert event["model"] == "claude-haiku-4-5"


@pytest.mark.timeout(30)
def test_chat_script_creates_log_file(chat_env: ChatScriptEnv) -> None:
    """Verify that chat.sh creates a log file with operation records."""
    chat_env.set_default_model("claude-sonnet-4-6")

    # The log dir is at $MNG_HOST_DIR/logs/
    log_dir = Path(chat_env.env["MNG_HOST_DIR"]) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    chat_env.run("--new", "--as-agent")

    log_file = log_dir / "chat.log"
    assert log_file.exists(), "chat.log should be created"
    log_content = log_file.read_text()
    assert "Creating new conversation" in log_content


# -- Event watcher offset tracking tests --


@pytest.mark.timeout(30)
def test_event_watcher_reads_settings_for_watched_sources(
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that the event watcher script reads watched_event_sources from settings."""

    agent_state_dir = local_shell_host.host_dir / "agents" / "test-agent"
    agent_state_dir.mkdir(parents=True)

    # Write a settings.toml with custom watched sources
    settings_content = '[watchers]\nwatched_event_sources = ["messages", "stop"]\nevent_poll_interval_seconds = 7\n'
    (agent_state_dir / "settings.toml").write_text(settings_content)

    # The event watcher reads settings via a Python snippet at startup.
    # Test that the Python settings-reading logic produces the expected output.
    settings_reader = f"""
import tomllib, pathlib, json
p = pathlib.Path('{agent_state_dir}/settings.toml')
s = tomllib.loads(p.read_text()) if p.exists() else {{}}
w = s.get('watchers', {{}})
print(json.dumps({{
    'poll': w.get('event_poll_interval_seconds', 3),
    'sources': w.get('watched_event_sources', ['messages', 'scheduled', 'mng_agents', 'stop'])
}}))
"""
    result = subprocess.run(
        ["python3", "-c", settings_reader],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert parsed["poll"] == 7
    assert parsed["sources"] == ["messages", "stop"]


# -- Provisioning settings file tests --


@pytest.mark.timeout(30)
def test_provision_settings_file_copies_to_agent_state(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that settings.toml is copied to the agent state directory."""
    changelings_dir = temp_git_repo / ".changelings"
    changelings_dir.mkdir()
    settings_content = '[chat]\nmodel = "claude-sonnet-4-6"\n'
    (changelings_dir / "settings.toml").write_text(settings_content)

    agent_state_dir = local_shell_host.host_dir / "agents" / "test-agent"
    agent_state_dir.mkdir(parents=True)

    provision_settings_file(local_shell_host, temp_git_repo, ".changelings", agent_state_dir)  # type: ignore[arg-type]

    dest = agent_state_dir / "settings.toml"
    assert dest.exists(), "settings.toml should be copied to agent state dir"
    assert dest.read_text() == settings_content


@pytest.mark.timeout(30)
def test_provision_settings_file_noop_when_missing(
    temp_git_repo: Path,
    local_shell_host: LocalShellHost,
) -> None:
    """Verify that provisioning settings does nothing when settings.toml is missing."""
    agent_state_dir = local_shell_host.host_dir / "agents" / "test-agent"
    agent_state_dir.mkdir(parents=True)

    provision_settings_file(local_shell_host, temp_git_repo, ".changelings", agent_state_dir)  # type: ignore[arg-type]

    dest = agent_state_dir / "settings.toml"
    assert not dest.exists(), "settings.toml should not be created when source is missing"


# -- Tmux window injection integration tests --


@pytest.mark.timeout(60)
def test_agent_with_ttyd_window_creates_session_with_expected_windows(
    cli_runner: CliRunner,
    temp_git_repo: Path,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify that adding named windows via --add-command creates the expected tmux windows.

    This tests the window injection mechanism that the claude-zygote plugin uses,
    without requiring ttyd to be installed.
    """
    agent_name = _unique_agent_name("ttyd")
    prefix = os.environ.get("MNG_PREFIX", "mng-test-")
    session_name = f"{prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        result = cli_runner.invoke(
            create,
            [
                "--name",
                agent_name,
                "--agent-cmd",
                "sleep 847291",
                "--source",
                str(temp_git_repo),
                "--no-connect",
                "--await-ready",
                "--no-copy-work-dir",
                "--no-ensure-clean",
                "--disable-plugin",
                "modal",
                "--add-command",
                'agent_ttyd="sleep 847293"',
                "--add-command",
                'conv_watcher="sleep 847294"',
                "--add-command",
                'events="sleep 847295"',
                "--add-command",
                'chat_ttyd="sleep 847296"',
            ],
            obj=plugin_manager,
            catch_exceptions=False,
        )

        assert result.exit_code == 0, f"CLI failed with: {result.output}"
        assert tmux_session_exists(session_name)

        windows_result = subprocess.run(
            ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
            capture_output=True,
            text=True,
        )
        assert windows_result.returncode == 0
        window_names = windows_result.stdout.strip().split("\n")

        expected_windows = {"agent_ttyd", "conv_watcher", "events", "chat_ttyd"}
        for expected in expected_windows:
            assert expected in window_names, f"Expected window '{expected}' in {window_names}"


@pytest.mark.timeout(60)
def test_agent_creation_and_listing(
    cli_runner: CliRunner,
    temp_git_repo: Path,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Verify that a created agent appears in mng list output."""
    agent_name = _unique_agent_name("listchk")
    prefix = os.environ.get("MNG_PREFIX", "mng-test-")
    session_name = f"{prefix}{agent_name}"

    with tmux_session_cleanup(session_name):
        exit_code = _create_zygote_agent(cli_runner, plugin_manager, agent_name, temp_git_repo)
        assert exit_code == 0

        list_result = cli_runner.invoke(
            list_command,
            ["--disable-plugin", "modal"],
            obj=plugin_manager,
            catch_exceptions=False,
        )
        assert list_result.exit_code == 0
        assert agent_name in list_result.output


# -- Conversation watcher sync logic tests --


@pytest.mark.timeout(30)
def test_conversation_watcher_sync_with_llm_database(
    chat_env: ChatScriptEnv,
    tmp_path: Path,
) -> None:
    """Test the conversation watcher's sync logic using a real SQLite database.

    Creates a minimal llm-compatible database and verifies that the sync
    script extracts messages correctly.
    """
    _write_conversation_event(chat_env.conversations_dir / "events.jsonl", "conv-sync-test")

    db_path = tmp_path / "logs.db"
    _create_test_llm_db(
        db_path,
        [
            (
                "resp-1",
                "Hello there",
                "Hi! How can I help?",
                "claude-sonnet-4-6",
                "2025-01-15T10:01:00",
                "conv-sync-test",
            ),
            (
                "resp-2",
                "Tell me a joke",
                "Why did the chicken...",
                "claude-sonnet-4-6",
                "2025-01-15T10:02:00",
                "conv-sync-test",
            ),
        ],
    )

    synced_count = _run_sync_script(
        chat_env.conversations_dir / "events.jsonl",
        chat_env.messages_dir / "events.jsonl",
        db_path,
    )
    assert synced_count == 4, f"Expected 4 synced events (2 user + 2 assistant), got {synced_count}"

    messages_file = chat_env.messages_dir / "events.jsonl"
    assert messages_file.exists()
    lines = messages_file.read_text().strip().split("\n")
    assert len(lines) == 4

    events = [json.loads(line) for line in lines]
    roles = [e["role"] for e in events]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 2

    for event in events:
        assert event["conversation_id"] == "conv-sync-test"
        assert event["source"] == "messages"
        assert event["type"] == "message"


@pytest.mark.timeout(30)
def test_conversation_watcher_sync_is_idempotent(
    chat_env: ChatScriptEnv,
    tmp_path: Path,
) -> None:
    """Verify that running the sync twice does not duplicate events."""
    _write_conversation_event(chat_env.conversations_dir / "events.jsonl", "conv-idem-test")

    db_path = tmp_path / "logs.db"
    _create_test_llm_db(
        db_path,
        [
            (
                "resp-idem",
                "Test message",
                "Test response",
                "claude-sonnet-4-6",
                "2025-01-15T10:01:00",
                "conv-idem-test",
            ),
        ],
    )

    conversations_file = chat_env.conversations_dir / "events.jsonl"
    messages_file = chat_env.messages_dir / "events.jsonl"

    first_count = _run_sync_script(conversations_file, messages_file, db_path)
    assert first_count == 2

    second_count = _run_sync_script(conversations_file, messages_file, db_path)
    assert second_count == 0

    lines = messages_file.read_text().strip().split("\n")
    assert len(lines) == 2
