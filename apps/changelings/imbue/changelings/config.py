from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

from imbue.changelings.data_types import ChangelingConfig
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.data_types import DEFAULT_SECRETS
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.errors import ChangelingNotFoundError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl

CONFIG_DIR_NAME: str = ".changelings"
CONFIG_FILE_NAME: str = "config.toml"


def get_config_dir() -> Path:
    """Get the changelings config directory path (~/.changelings/)."""
    return Path.home() / CONFIG_DIR_NAME


def get_config_path() -> Path:
    """Get the changelings config file path (~/.changelings/config.toml)."""
    return get_config_dir() / CONFIG_FILE_NAME


def load_config() -> ChangelingConfig:
    """Load the changelings config from disk.

    Returns an empty config if the config file does not exist.
    Raises ChangelingConfigError if the file exists but cannot be parsed.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return ChangelingConfig()

    try:
        raw = tomlkit.loads(config_path.read_text())
    except TOMLKitError as e:
        raise ChangelingConfigError(f"Failed to parse config file {config_path}: {e}") from e

    return _parse_config(raw)


def save_config(config: ChangelingConfig) -> None:
    """Write the changelings config to disk.

    Creates the config directory if it does not exist.
    """
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    raw = _serialize_config(config)
    config_path.write_text(tomlkit.dumps(raw))


def add_changeling(definition: ChangelingDefinition) -> ChangelingConfig:
    """Add a new changeling to the config and save it.

    Raises ChangelingAlreadyExistsError if a changeling with that name already exists.
    """
    config = load_config()
    if definition.name in config.changeling_by_name:
        raise ChangelingAlreadyExistsError(str(definition.name))

    updated = ChangelingConfig(
        changeling_by_name={**config.changeling_by_name, definition.name: definition},
    )
    save_config(updated)
    return updated


def upsert_changeling(definition: ChangelingDefinition) -> ChangelingConfig:
    """Add or update a changeling in the config and save it.

    Creates the changeling if it doesn't exist, or replaces it if it does.
    """
    config = load_config()
    updated = ChangelingConfig(
        changeling_by_name={**config.changeling_by_name, definition.name: definition},
    )
    save_config(updated)
    return updated


def remove_changeling(name: ChangelingName) -> ChangelingConfig:
    """Remove a changeling from the config and save it.

    Raises ChangelingNotFoundError if the changeling does not exist.
    """
    config = load_config()
    if name not in config.changeling_by_name:
        raise ChangelingNotFoundError(str(name))

    remaining = {k: v for k, v in config.changeling_by_name.items() if k != name}
    updated = ChangelingConfig(changeling_by_name=remaining)
    save_config(updated)
    return updated


def get_changeling(name: ChangelingName) -> ChangelingDefinition:
    """Get a changeling by name from the config.

    Raises ChangelingNotFoundError if the changeling does not exist.
    """
    config = load_config()
    if name not in config.changeling_by_name:
        raise ChangelingNotFoundError(str(name))
    return config.changeling_by_name[name]


def _parse_config(raw: dict) -> ChangelingConfig:
    """Parse a raw TOML dict into a ChangelingConfig."""
    changelings_raw = raw.get("changelings", {})
    changeling_by_name: dict[ChangelingName, ChangelingDefinition] = {}

    for name_str, fields in changelings_raw.items():
        changeling_name = ChangelingName(name_str)
        # Convert TOML dict to ChangelingDefinition, adding the name
        definition_data = dict(fields)
        definition_data["name"] = changeling_name

        # Default agent_type to the changeling name (per design.md)
        if "agent_type" not in definition_data:
            definition_data["agent_type"] = str(changeling_name)

        # Parse typed fields
        if "schedule" in definition_data:
            definition_data["schedule"] = CronSchedule(definition_data["schedule"])
        if "repo" in definition_data and definition_data["repo"] is not None:
            definition_data["repo"] = GitRepoUrl(definition_data["repo"])

        # Parse list fields
        if "secrets" in definition_data:
            definition_data["secrets"] = tuple(definition_data["secrets"])

        # Map TOML field names to model field names
        if "enabled" in definition_data:
            definition_data["is_enabled"] = definition_data.pop("enabled")

        changeling_by_name[changeling_name] = ChangelingDefinition(**definition_data)

    return ChangelingConfig(changeling_by_name=changeling_by_name)


def _serialize_config(config: ChangelingConfig) -> dict:
    """Serialize a ChangelingConfig to a TOML-compatible dict."""
    doc = tomlkit.document()
    changelings_table = tomlkit.table(is_super_table=True)

    for name, definition in config.changeling_by_name.items():
        entry = tomlkit.table()
        entry.add("agent_type", definition.agent_type)
        entry.add("schedule", str(definition.schedule))
        entry.add("branch", definition.branch)
        entry.add("enabled", definition.is_enabled)

        if definition.repo is not None:
            entry.add("repo", str(definition.repo))
        if definition.initial_message != DEFAULT_INITIAL_MESSAGE:
            entry.add("initial_message", definition.initial_message)
        if definition.secrets != DEFAULT_SECRETS:
            entry.add("secrets", list(definition.secrets))
        if definition.extra_mngr_args:
            entry.add("extra_mngr_args", definition.extra_mngr_args)
        if definition.env_vars:
            entry.add("env_vars", dict(definition.env_vars))
        if definition.mngr_options:
            entry.add("mngr_options", dict(definition.mngr_options))

        changelings_table.add(str(name), entry)

    doc.add("changelings", changelings_table)
    return doc
