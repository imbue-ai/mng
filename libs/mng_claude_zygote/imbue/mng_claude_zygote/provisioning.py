from __future__ import annotations

import importlib.resources
import shlex
import time
from pathlib import Path
from typing import Final

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mng.interfaces.data_types import CommandResult
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng_claude_zygote import resources as zygote_resources
from imbue.mng_claude_zygote.data_types import ChatModel

# Scripts to provision to $MNG_HOST_DIR/commands/
_SCRIPT_FILES: Final[tuple[str, ...]] = (
    "chat.sh",
    "conversation_watcher.sh",
    "event_watcher.sh",
)

# Python tool files to provision to $MNG_HOST_DIR/commands/llm_tools/
_LLM_TOOL_FILES: Final[tuple[str, ...]] = (
    "context_tool.py",
    "extra_context_tool.py",
)

# Timeout thresholds (seconds).
# Hard timeout = command is definitely broken if it takes this long.
# Warn threshold = emit a warning if the command takes longer than this.
_FS_HARD_TIMEOUT: Final[float] = 15.0
_FS_WARN_THRESHOLD: Final[float] = 2.0
_COMMAND_CHECK_HARD_TIMEOUT: Final[float] = 30.0
_COMMAND_CHECK_WARN_THRESHOLD: Final[float] = 5.0
_INSTALL_HARD_TIMEOUT: Final[float] = 300.0
_INSTALL_WARN_THRESHOLD: Final[float] = 60.0


def _execute_with_timing(
    host: OnlineHostInterface,
    cmd: str,
    *,
    hard_timeout: float,
    warn_threshold: float,
    label: str,
) -> CommandResult:
    """Execute a host command with two-threshold timeout monitoring.

    Uses hard_timeout as the actual timeout. If the command takes longer
    than warn_threshold, emits a warning so we can notice degradation
    before it becomes an outright failure.
    """
    start = time.monotonic()
    result = host.execute_command(cmd, timeout_seconds=hard_timeout)
    elapsed = time.monotonic() - start
    if elapsed > warn_threshold:
        logger.warning("{} took {:.1f}s (expected <{:.0f}s): {}", label, elapsed, warn_threshold, cmd)
    return result


def load_zygote_resource(filename: str) -> str:
    """Load a resource file from the mng_claude_zygote resources package."""
    resource_files = importlib.resources.files(zygote_resources)
    resource_path = resource_files.joinpath(filename)
    return resource_path.read_text()


def install_llm_toolchain(host: OnlineHostInterface) -> None:
    """Install llm, llm-anthropic, and llm-live-chat on the host.

    Uses uv tool install for llm itself, then llm install for plugins.
    Skips installation if llm is already available.
    """
    with log_span("Installing llm toolchain"):
        # Check if llm is already installed
        check_result = _execute_with_timing(
            host,
            "command -v llm",
            hard_timeout=_COMMAND_CHECK_HARD_TIMEOUT,
            warn_threshold=_COMMAND_CHECK_WARN_THRESHOLD,
            label="llm check",
        )
        if check_result.success:
            # llm is installed, just ensure plugins are present
            _install_llm_plugins(host)
            return

        # Install llm via uv tool
        result = _execute_with_timing(
            host,
            "uv tool install llm",
            hard_timeout=_INSTALL_HARD_TIMEOUT,
            warn_threshold=_INSTALL_WARN_THRESHOLD,
            label="llm install",
        )
        if not result.success:
            raise RuntimeError(f"Failed to install llm: {result.stderr}")

        _install_llm_plugins(host)


def _install_llm_plugins(host: OnlineHostInterface) -> None:
    """Install llm-anthropic and llm-live-chat plugins."""
    for plugin_name in ("llm-anthropic", "llm-live-chat"):
        with log_span("Installing llm plugin: {}", plugin_name):
            result = _execute_with_timing(
                host,
                f"llm install {plugin_name}",
                hard_timeout=_INSTALL_HARD_TIMEOUT,
                warn_threshold=_INSTALL_WARN_THRESHOLD,
                label=f"llm plugin install ({plugin_name})",
            )
            if not result.success:
                raise RuntimeError(f"Failed to install {plugin_name}: {result.stderr}")


def create_changeling_symlinks(host: OnlineHostInterface, work_dir: Path, changelings_dir_name: str) -> None:
    """Create symlinks from changeling entrypoint files to their expected locations.

    Creates:
    - <work_dir>/CLAUDE.local.md -> <work_dir>/<changelings_dir>/entrypoint.md
    - <work_dir>/.claude/settings.local.json -> <work_dir>/<changelings_dir>/entrypoint.json
    """
    changelings_dir = work_dir / changelings_dir_name

    _create_symlink_if_target_exists(
        host,
        link_path=work_dir / "CLAUDE.local.md",
        target_path=changelings_dir / "entrypoint.md",
    )

    _create_symlink_if_target_exists(
        host,
        link_path=work_dir / ".claude" / "settings.local.json",
        target_path=changelings_dir / "entrypoint.json",
    )


def _create_symlink_if_target_exists(host: OnlineHostInterface, link_path: Path, target_path: Path) -> None:
    """Create a symlink at link_path pointing to target_path, if target exists."""
    check = _execute_with_timing(
        host,
        f"test -f {shlex.quote(str(target_path))}",
        hard_timeout=_FS_HARD_TIMEOUT,
        warn_threshold=_FS_WARN_THRESHOLD,
        label="file check",
    )
    if not check.success:
        return

    # Ensure parent directory exists
    _execute_with_timing(
        host,
        f"mkdir -p {shlex.quote(str(link_path.parent))}",
        hard_timeout=_FS_HARD_TIMEOUT,
        warn_threshold=_FS_WARN_THRESHOLD,
        label="mkdir",
    )

    # Create symlink (force to overwrite existing)
    cmd = f"ln -sf {shlex.quote(str(target_path))} {shlex.quote(str(link_path))}"
    with log_span("Creating symlink: {} -> {}", link_path, target_path):
        result = _execute_with_timing(
            host,
            cmd,
            hard_timeout=_FS_HARD_TIMEOUT,
            warn_threshold=_FS_WARN_THRESHOLD,
            label="symlink",
        )
        if not result.success:
            raise RuntimeError(f"Failed to create symlink {link_path} -> {target_path}: {result.stderr}")


def provision_changeling_scripts(host: OnlineHostInterface) -> None:
    """Write changeling bash scripts to $MNG_HOST_DIR/commands/.

    Scripts are loaded from the resources package and written with execute permission.
    """
    commands_dir = host.host_dir / "commands"
    _execute_with_timing(
        host,
        f"mkdir -p {shlex.quote(str(commands_dir))}",
        hard_timeout=_FS_HARD_TIMEOUT,
        warn_threshold=_FS_WARN_THRESHOLD,
        label="mkdir commands",
    )

    for script_name in _SCRIPT_FILES:
        script_content = load_zygote_resource(script_name)
        script_path = commands_dir / script_name
        with log_span("Writing {} to host", script_name):
            host.write_file(script_path, script_content.encode(), mode="0755")


def provision_llm_tools(host: OnlineHostInterface) -> None:
    """Write LLM tool Python files to $MNG_HOST_DIR/commands/llm_tools/.

    These files are passed to `llm live-chat` via `--functions` to give
    conversation agents access to changeling context.
    """
    tools_dir = host.host_dir / "commands" / "llm_tools"
    _execute_with_timing(
        host,
        f"mkdir -p {shlex.quote(str(tools_dir))}",
        hard_timeout=_FS_HARD_TIMEOUT,
        warn_threshold=_FS_WARN_THRESHOLD,
        label="mkdir llm_tools",
    )

    for tool_file in _LLM_TOOL_FILES:
        tool_content = load_zygote_resource(tool_file)
        tool_path = tools_dir / tool_file
        with log_span("Writing {} to host", tool_file):
            host.write_file(tool_path, tool_content.encode(), mode="0644")


def create_event_log_directories(host: OnlineHostInterface, agent_state_dir: Path) -> None:
    """Create the event log directory structure.

    Creates directories for each event source:
    - <agent_state_dir>/logs/conversations/  (conversation lifecycle events)
    - <agent_state_dir>/logs/messages/       (conversation messages)
    - <agent_state_dir>/logs/entrypoint/     (entrypoint trigger events)
    - <agent_state_dir>/logs/transcript/     (inner monologue, written by Claude background tasks)
    """
    for source in ("conversations", "messages", "entrypoint", "transcript"):
        source_dir = agent_state_dir / "logs" / source
        _execute_with_timing(
            host,
            f"mkdir -p {shlex.quote(str(source_dir))}",
            hard_timeout=_FS_HARD_TIMEOUT,
            warn_threshold=_FS_WARN_THRESHOLD,
            label=f"mkdir logs/{source}",
        )


def write_default_chat_model(host: OnlineHostInterface, agent_state_dir: Path, model: ChatModel) -> None:
    """Write the default chat model to the agent state directory."""
    model_file = agent_state_dir / "default_chat_model"
    host.write_text_file(model_file, str(model) + "\n")


def compute_claude_project_dir_name(work_dir_abs: str) -> str:
    """Compute the Claude project directory name from an absolute work_dir path.

    Claude names project directories by replacing '/' and '.' with '-' in the
    absolute path, e.g. /home/user/.changelings/my-agent -> -home-user--changelings-my-agent
    """
    return work_dir_abs.replace("/", "-").replace(".", "-")


def link_memory_directory(host: OnlineHostInterface, work_dir: Path, changelings_dir_name: str) -> None:
    """Symlink the changelings memory directory into the Claude project memory path.

    Creates:
    - <work_dir>/<changelings_dir>/memory/ (if it doesn't exist)
    - ~/.claude/projects/<project_name>/memory/ -> <work_dir>/<changelings_dir>/memory/

    This ensures all Claude agents share the same project memory, and that
    memories are version-controlled in the agent's git repo.
    """
    changelings_memory = work_dir / changelings_dir_name / "memory"

    # Get the absolute path of work_dir on the host
    abs_result = _execute_with_timing(
        host,
        f"cd {shlex.quote(str(work_dir))} && pwd",
        hard_timeout=_FS_HARD_TIMEOUT,
        warn_threshold=_FS_WARN_THRESHOLD,
        label="resolve work_dir",
    )
    if not abs_result.success:
        raise RuntimeError(f"Failed to resolve absolute path of {work_dir}: {abs_result.stderr}")
    abs_work_dir = abs_result.stdout.strip()
    project_dir_name = compute_claude_project_dir_name(abs_work_dir)

    # Create the changelings memory directory
    _execute_with_timing(
        host,
        f"mkdir -p {shlex.quote(str(changelings_memory))}",
        hard_timeout=_FS_HARD_TIMEOUT,
        warn_threshold=_FS_WARN_THRESHOLD,
        label="mkdir changelings memory",
    )

    # Create the Claude project directory and symlink memory into it.
    # Use $HOME instead of ~ because ~ is not expanded inside single quotes
    # (which shlex.quote produces), but $HOME expands in double quotes.
    quoted_project_dir_name = shlex.quote(project_dir_name)
    project_dir_shell = f'"$HOME/.claude/projects/"{quoted_project_dir_name}'
    memory_link_shell = f'"$HOME/.claude/projects/"{quoted_project_dir_name}/memory'

    cmd = f"mkdir -p {project_dir_shell} && ln -sfn {shlex.quote(str(changelings_memory))} {memory_link_shell}"
    with log_span("Linking memory: $HOME/.claude/projects/{}/memory -> {}", project_dir_name, changelings_memory):
        result = _execute_with_timing(
            host,
            cmd,
            hard_timeout=_FS_HARD_TIMEOUT,
            warn_threshold=_FS_WARN_THRESHOLD,
            label="link memory",
        )
        if not result.success:
            raise RuntimeError(f"Failed to link memory directory: {result.stderr}")
