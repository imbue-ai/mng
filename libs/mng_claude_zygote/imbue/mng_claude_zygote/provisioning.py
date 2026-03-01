from __future__ import annotations

import importlib.resources
import shlex
from pathlib import Path

from imbue.imbue_common.logging import log_span
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng_claude_zygote import resources as zygote_resources
from imbue.mng_claude_zygote.data_types import ChatModel

# Scripts to provision to $MNG_HOST_DIR/commands/
_SCRIPT_FILES = (
    "chat.sh",
    "conversation_watcher.sh",
    "event_watcher.sh",
)

# Python tool files to provision to $MNG_HOST_DIR/commands/llm_tools/
_LLM_TOOL_FILES = (
    "context_tool.py",
    "extra_context_tool.py",
)


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
        check_result = host.execute_command("command -v llm", timeout_seconds=10.0)
        if check_result.success:
            # llm is installed, just ensure plugins are present
            _install_llm_plugins(host)
            return

        # Install llm via uv tool
        result = host.execute_command("uv tool install llm", timeout_seconds=120.0)
        if not result.success:
            raise RuntimeError(f"Failed to install llm: {result.stderr}")

        _install_llm_plugins(host)


def _install_llm_plugins(host: OnlineHostInterface) -> None:
    """Install llm-anthropic and llm-live-chat plugins."""
    for plugin_name in ("llm-anthropic", "llm-live-chat"):
        with log_span("Installing llm plugin: {}", plugin_name):
            result = host.execute_command(f"llm install {plugin_name}", timeout_seconds=120.0)
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
    check = host.execute_command(f"test -f {shlex.quote(str(target_path))}", timeout_seconds=5.0)
    if not check.success:
        return

    # Ensure parent directory exists
    host.execute_command(f"mkdir -p {shlex.quote(str(link_path.parent))}", timeout_seconds=5.0)

    # Create symlink (force to overwrite existing)
    cmd = f"ln -sf {shlex.quote(str(target_path))} {shlex.quote(str(link_path))}"
    with log_span("Creating symlink: {} -> {}", link_path, target_path):
        result = host.execute_command(cmd, timeout_seconds=5.0)
        if not result.success:
            raise RuntimeError(f"Failed to create symlink {link_path} -> {target_path}: {result.stderr}")


def provision_changeling_scripts(host: OnlineHostInterface) -> None:
    """Write changeling bash scripts to $MNG_HOST_DIR/commands/.

    Scripts are loaded from the resources package and written with execute permission.
    """
    commands_dir = host.host_dir / "commands"
    host.execute_command(f"mkdir -p {shlex.quote(str(commands_dir))}", timeout_seconds=5.0)

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
    host.execute_command(f"mkdir -p {shlex.quote(str(tools_dir))}", timeout_seconds=5.0)

    for tool_file in _LLM_TOOL_FILES:
        tool_content = load_zygote_resource(tool_file)
        tool_path = tools_dir / tool_file
        with log_span("Writing {} to host", tool_file):
            host.write_file(tool_path, tool_content.encode(), mode="0644")


def create_conversation_directories(host: OnlineHostInterface, agent_state_dir: Path) -> None:
    """Create the conversation log directory structure.

    Creates:
    - <agent_state_dir>/logs/conversations/
    """
    conversations_dir = agent_state_dir / "logs" / "conversations"
    host.execute_command(f"mkdir -p {shlex.quote(str(conversations_dir))}", timeout_seconds=5.0)


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
    abs_result = host.execute_command(
        f"cd {shlex.quote(str(work_dir))} && pwd",
        timeout_seconds=5.0,
    )
    if not abs_result.success:
        raise RuntimeError(f"Failed to resolve absolute path of {work_dir}: {abs_result.stderr}")
    abs_work_dir = abs_result.stdout.strip()

    project_dir_name = compute_claude_project_dir_name(abs_work_dir)

    # Create the changelings memory directory
    host.execute_command(f"mkdir -p {shlex.quote(str(changelings_memory))}", timeout_seconds=5.0)

    # Create the Claude project directory and symlink memory into it
    project_dir = Path("~/.claude/projects") / project_dir_name
    memory_link = project_dir / "memory"

    cmd = (
        f"mkdir -p {shlex.quote(str(project_dir))} && "
        f"ln -sfn {shlex.quote(str(changelings_memory))} {shlex.quote(str(memory_link))}"
    )
    with log_span("Linking memory: {} -> {}", memory_link, changelings_memory):
        result = host.execute_command(cmd, timeout_seconds=5.0)
        if not result.success:
            raise RuntimeError(f"Failed to link memory directory: {result.stderr}")
