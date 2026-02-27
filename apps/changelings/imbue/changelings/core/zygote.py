import tomllib
from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic import model_validator

from imbue.changelings.errors import ChangelingError
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.primitives import NonEmptyStr
from imbue.imbue_common.primitives import PositiveInt
from imbue.mng.primitives import AgentTypeName

ZYGOTE_CONFIG_FILENAME: Final[str] = "changeling.toml"


class ZygoteName(NonEmptyStr):
    """Name of a changeling zygote (used as the default agent name)."""

    ...


class ZygoteCommand(NonEmptyStr):
    """Shell command to start the changeling's server process."""

    ...


class ZygoteConfig(FrozenModel):
    """Configuration for a changeling zygote, read from changeling.toml.

    Either `agent_type` must be set (for agent-type-based changelings like elena-code),
    or both `command` and `port` must be set (for custom-command changelings like hello-world).
    """

    name: ZygoteName = Field(description="Default name for the changeling")
    agent_type: AgentTypeName | None = Field(
        default=None,
        description="mng agent type to use (e.g. 'elena-code'). When set, command and port are handled by the agent type.",
    )
    command: ZygoteCommand | None = Field(
        default=None,
        description="Shell command to start the changeling's server",
    )
    port: PositiveInt | None = Field(
        default=None,
        description="Port the changeling's HTTP server listens on",
    )
    description: str = Field(default="", description="Human-readable description of the changeling")

    @model_validator(mode="after")
    def _validate_command_or_agent_type(self) -> "ZygoteConfig":
        """Validate that either agent_type or both command and port are set."""
        if self.agent_type is None:
            if self.command is None:
                raise ValueError("'command' is required when 'agent_type' is not set")
            if self.port is None:
                raise ValueError("'port' is required when 'agent_type' is not set")
        return self


class ZygoteNotFoundError(ChangelingError):
    """Raised when a zygote config file cannot be found at the expected path."""

    ...


class ZygoteConfigError(ChangelingError):
    """Raised when a zygote config file has invalid or missing fields."""

    ...


def load_zygote_config(zygote_dir: Path) -> ZygoteConfig:
    """Load and validate a ZygoteConfig from a changeling.toml file in the given directory."""
    config_path = zygote_dir / ZYGOTE_CONFIG_FILENAME

    if not config_path.exists():
        raise ZygoteNotFoundError("No {} found in {}".format(ZYGOTE_CONFIG_FILENAME, zygote_dir))

    try:
        raw = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ZygoteConfigError("Invalid TOML in {}: {}".format(config_path, e)) from e

    changeling_section = raw.get("changeling")
    if changeling_section is None:
        raise ZygoteConfigError("Missing [changeling] section in {}".format(config_path))

    if not isinstance(changeling_section, dict):
        raise ZygoteConfigError("[changeling] section in {} must be a table".format(config_path))

    try:
        return ZygoteConfig.model_validate(changeling_section)
    except (ValueError, TypeError, KeyError) as e:
        raise ZygoteConfigError("Invalid changeling config in {}: {}".format(config_path, e)) from e
