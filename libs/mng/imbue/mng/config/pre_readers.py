import os
import tomllib
from pathlib import Path
from typing import Any
from typing import Final

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.errors import ProcessError

# Constants duplicated from data_types.py to avoid importing heavy dependencies
# (data_types pulls in pydantic, pluggy, and the full config model hierarchy).
PROFILES_DIRNAME: Final[str] = "profiles"
ROOT_CONFIG_FILENAME: Final[str] = "config.toml"


# =============================================================================
# Config File Discovery
# =============================================================================


def _load_toml(path: Path) -> dict[str, Any] | None:
    """Load and parse a TOML file, returning None if the file is missing or malformed."""
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError:
        return None


def find_profile_dir_lightweight(base_dir: Path) -> Path | None:
    """Read-only profile directory lookup (never creates dirs/files).

    Returns the profile directory if it can be determined from existing files,
    or None otherwise.
    """
    config_path = base_dir / ROOT_CONFIG_FILENAME
    if not config_path.exists():
        return None
    try:
        with open(config_path, "rb") as f:
            root_config = tomllib.load(f)
        profile_id = root_config.get("profile")
        if not profile_id:
            return None
        profile_dir = base_dir / PROFILES_DIRNAME / profile_id
        if profile_dir.exists() and profile_dir.is_dir():
            return profile_dir
    except tomllib.TOMLDecodeError:
        pass
    return None


def get_user_config_path(profile_dir: Path) -> Path:
    """Get the user config path based on profile directory."""
    return profile_dir / "settings.toml"


def _get_project_config_name(root_name: str) -> Path:
    """Get the project config relative path based on root name."""
    return Path(f".{root_name}") / "settings.toml"


def _get_local_config_name(root_name: str) -> Path:
    """Get the local config relative path based on root name."""
    return Path(f".{root_name}") / "settings.local.toml"


def _find_project_root(cg: ConcurrencyGroup, start: Path | None = None) -> Path | None:
    """Find the project root by looking for git worktree root.

    Inlined from git_utils.find_git_worktree_root to avoid importing
    loguru (which git_utils depends on).
    """
    cwd = start or Path.cwd()
    try:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
        )
        return Path(result.stdout.strip())
    except ProcessError:
        return None


def find_project_config(context_dir: Path | None, root_name: str, cg: ConcurrencyGroup) -> Path | None:
    """Find the project config file."""
    root = context_dir or _find_project_root(cg=cg)
    if root is None:
        return None
    config_path = root / _get_project_config_name(root_name)
    return config_path if config_path.exists() else None


def find_local_config(context_dir: Path | None, root_name: str, cg: ConcurrencyGroup) -> Path | None:
    """Find the local config file."""
    root = context_dir or _find_project_root(cg=cg)
    if root is None:
        return None
    config_path = root / _get_local_config_name(root_name)
    return config_path if config_path.exists() else None


# =============================================================================
# Lightweight config pre-readers
# =============================================================================
#
# These functions read specific values from config files before the full
# config is loaded.  They run early in startup (CLI parse time or plugin
# manager creation) so they intentionally avoid plugin hooks, full config
# validation, and anything that needs a PluginManager.
#
# Note: logging is not yet configured when these run (setup_logging needs
# OutputOptions and MngContext, which aren't available until after config
# loading).
#
# _resolve_config_file_paths returns the existing config file paths in
# precedence order (user, project, local). Each pre-reader calls its own
# per-file loader and merges the results via dict comprehension, so later
# layers naturally override earlier ones.


def _resolve_config_file_paths() -> list[Path]:
    """Return existing config file paths in precedence order (lowest to highest)."""
    root_name = os.environ.get("MNG_ROOT_NAME", "mng")
    env_host_dir = os.environ.get("MNG_HOST_DIR")
    base_dir = Path(env_host_dir) if env_host_dir else Path(f"~/.{root_name}")
    base_dir = base_dir.expanduser()

    paths: list[Path] = []

    # User config
    profile_dir = find_profile_dir_lightweight(base_dir)
    if profile_dir is not None:
        user_config_path = get_user_config_path(profile_dir)
        if user_config_path.exists():
            paths.append(user_config_path)

    # Project + local config need the project root
    cg = ConcurrencyGroup(name="config-pre-reader")
    with cg:
        project_config_path = find_project_config(None, root_name, cg)
        local_config_path = find_local_config(None, root_name, cg)

    if project_config_path is not None:
        paths.append(project_config_path)

    if local_config_path is not None:
        paths.append(local_config_path)

    return paths


# --- Default subcommand pre-reader ---


def read_default_command(command_name: str) -> str:
    """Return the configured default subcommand for command_name.

    If no config files set default_subcommand for the given command
    group, falls back to "create".  An empty string means "disabled"
    (the caller should show help instead of defaulting).
    """
    merged = dict(
        item for path in _resolve_config_file_paths() for item in _load_default_subcommands_from_file(path).items()
    )
    return merged.get(command_name, "create")


def _load_default_subcommands_from_file(path: Path) -> dict[str, str]:
    """Extract default_subcommand entries from a TOML config file."""
    raw = _load_toml(path)
    if raw is None:
        return {}
    raw_commands = raw.get("commands")
    if not isinstance(raw_commands, dict):
        return {}
    result: dict[str, str] = {}
    for cmd_name, cmd_section in raw_commands.items():
        if not isinstance(cmd_section, dict):
            continue
        value = cmd_section.get("default_subcommand")
        if value is not None:
            result[cmd_name] = str(value)
    return result


# --- Disabled plugins pre-reader ---


def read_disabled_plugins() -> frozenset[str]:
    """Return the set of plugin names disabled across all config layers.

    Reads user, project, and local config files for [plugins.<name>]
    sections with enabled = false.  Later layers override earlier ones.
    """
    merged = dict(
        item for path in _resolve_config_file_paths() for item in _load_disabled_plugins_from_file(path).items()
    )
    return frozenset(name for name, is_enabled in merged.items() if not is_enabled)


def _load_disabled_plugins_from_file(path: Path) -> dict[str, bool]:
    """Extract plugin enabled/disabled state from a TOML config file."""
    raw = _load_toml(path)
    if raw is None:
        return {}
    raw_plugins = raw.get("plugins")
    if not isinstance(raw_plugins, dict):
        return {}
    result: dict[str, bool] = {}
    for plugin_name, plugin_section in raw_plugins.items():
        if not isinstance(plugin_section, dict):
            continue
        enabled_value = plugin_section.get("enabled")
        if enabled_value is not None:
            result[plugin_name] = bool(enabled_value)
    return result


# --- Default host dir pre-reader ---


def read_default_host_dir() -> Path:
    """Return the configured default host directory, expanded to an absolute path.

    Precedence (highest to lowest):
    1. MNG_HOST_DIR environment variable
    2. default_host_dir from config files (user -> project -> local, last wins)
    3. ~/.{root_name} fallback (root_name from MNG_ROOT_NAME, defaults to "mng")
    """
    env_host_dir = os.environ.get("MNG_HOST_DIR")
    if env_host_dir:
        return Path(env_host_dir).expanduser()

    # Read from config files in precedence order (lowest to highest).
    # Later values override earlier ones.
    host_dir: str | None = None
    for path in _resolve_config_file_paths():
        raw = _load_toml(path)
        if raw is None:
            continue
        value = raw.get("default_host_dir")
        if value is not None:
            host_dir = str(value)

    if host_dir is not None:
        return Path(host_dir).expanduser()

    # Fall back to ~/.{root_name}
    root_name = os.environ.get("MNG_ROOT_NAME", "mng")
    return Path(f"~/.{root_name}").expanduser()
