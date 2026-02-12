from pathlib import Path
from typing import Any
from typing import Final

import tomlkit

from imbue.changelings.data_types import ChangelingConfig
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingAlreadyExistsError
from imbue.changelings.errors import ChangelingConfigError
from imbue.changelings.errors import ChangelingNotFoundError
from imbue.changelings.primitives import ChangelingName
from imbue.imbue_common.pure import pure

DEFAULT_CONFIG_DIR: Final[Path] = Path.home() / ".changelings"
DEFAULT_CONFIG_PATH: Final[Path] = DEFAULT_CONFIG_DIR / "config.toml"


def get_default_config_path() -> Path:
    """Get the default config file path (~/.changelings/config.toml)."""
    return Path.home() / ".changelings" / "config.toml"


def load_config(config_path: Path) -> ChangelingConfig:
    """Load changeling configuration from a TOML file.

    Returns an empty config if the file does not exist.
    """
    if not config_path.exists():
        return ChangelingConfig()

    try:
        with open(config_path, "rb") as f:
            import tomllib

            raw = tomllib.load(f)
    except Exception as e:
        raise ChangelingConfigError(f"Failed to load config from {config_path}: {e}") from e

    return _parse_config(raw)


def save_config(config: ChangelingConfig, config_path: Path) -> None:
    """Save changeling configuration to a TOML file.

    Creates the parent directory if it does not exist.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    doc = _config_to_toml(config)

    with open(config_path, "w") as f:
        tomlkit.dump(doc, f)


@pure
def add_changeling(config: ChangelingConfig, definition: ChangelingDefinition) -> ChangelingConfig:
    """Add a changeling definition to the config.

    Raises ChangelingAlreadyExistsError if a changeling with the same name already exists.
    """
    if definition.name in config.changeling_by_name:
        raise ChangelingAlreadyExistsError(definition.name)

    new_changeling_by_name = dict(config.changeling_by_name)
    new_changeling_by_name[definition.name] = definition
    return ChangelingConfig(changeling_by_name=new_changeling_by_name)


@pure
def remove_changeling(config: ChangelingConfig, name: ChangelingName) -> ChangelingConfig:
    """Remove a changeling definition from the config.

    Raises ChangelingNotFoundError if the changeling does not exist.
    """
    if name not in config.changeling_by_name:
        raise ChangelingNotFoundError(name)

    new_changeling_by_name = {k: v for k, v in config.changeling_by_name.items() if k != name}
    return ChangelingConfig(changeling_by_name=new_changeling_by_name)


@pure
def _parse_config(raw: dict[str, Any]) -> ChangelingConfig:
    """Parse a raw TOML dict into a ChangelingConfig."""
    changelings_raw = raw.get("changelings", {})
    if not isinstance(changelings_raw, dict):
        raise ChangelingConfigError("'changelings' must be a table")

    changeling_by_name: dict[ChangelingName, ChangelingDefinition] = {}
    for name_str, values in changelings_raw.items():
        if not isinstance(values, dict):
            raise ChangelingConfigError(f"Changeling '{name_str}' must be a table")

        try:
            name = ChangelingName(name_str)
            definition = ChangelingDefinition(name=name, **values)
            changeling_by_name[name] = definition
        except Exception as e:
            raise ChangelingConfigError(f"Invalid changeling '{name_str}': {e}") from e

    return ChangelingConfig(changeling_by_name=changeling_by_name)


@pure
def _config_to_toml(config: ChangelingConfig) -> tomlkit.TOMLDocument:
    """Convert a ChangelingConfig to a tomlkit TOMLDocument for serialization."""
    doc = tomlkit.document()

    if not config.changeling_by_name:
        return doc

    changelings_table = tomlkit.table(is_super_table=True)

    for name, definition in sorted(config.changeling_by_name.items()):
        entry = tomlkit.table()
        entry.add("template", str(definition.template))
        entry.add("schedule", str(definition.schedule))
        entry.add("repo", str(definition.repo))

        if definition.branch != "main":
            entry.add("branch", definition.branch)
        if definition.message is not None:
            entry.add("message", definition.message)
        if definition.agent_type != "claude":
            entry.add("agent_type", definition.agent_type)
        if definition.extra_mngr_args:
            entry.add("extra_mngr_args", definition.extra_mngr_args)
        if definition.env_vars:
            entry.add("env_vars", definition.env_vars)
        if not definition.is_enabled:
            entry.add("is_enabled", False)

        changelings_table.add(str(name), entry)

    doc.add("changelings", changelings_table)
    return doc
