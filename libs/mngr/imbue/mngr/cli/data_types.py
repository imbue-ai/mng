from typing import Any

import click
from click_option_group import GroupedOption
from click_option_group import OptionGroup
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel


class OptionStackItem(FrozenModel):
    """Specification for a CLI option that plugins can register.

    This provides a typed interface for plugins to add custom CLI options
    to mngr subcommands. The fields correspond to click.Option parameters.
    """

    param_decls: tuple[str, ...] = Field(description="Option names, e.g. ('--my-option', '-m')")
    type: Any = Field(
        default=str,
        description="The click type for the option value",
    )
    default: Any = Field(
        default=None,
        description="Default value if option not provided",
    )
    help: str | None = Field(
        default=None,
        description="Help text shown in --help output",
    )
    is_flag: bool = Field(
        default=False,
        description="Whether this is a boolean flag (no value needed)",
    )
    multiple: bool = Field(
        default=False,
        description="Whether the option can be specified multiple times",
    )
    required: bool = Field(
        default=False,
        description="Whether the option is required",
    )
    envvar: str | None = Field(
        default=None,
        description="Environment variable to read value from",
    )

    def to_click_option(self, group: OptionGroup | None = None) -> click.Option:
        """Convert this spec to a click.Option instance.

        If a group is provided, returns a GroupedOption that belongs to that group.
        Otherwise returns a regular click.Option.
        """
        option_class: type[click.Option] = GroupedOption if group else click.Option
        group_kwargs: dict[str, Any] = {"group": group} if group else {}

        # For flag options, don't pass type - click handles it internally
        if self.is_flag:
            return option_class(
                self.param_decls,
                default=self.default,
                help=self.help,
                is_flag=True,
                multiple=self.multiple,
                required=self.required,
                envvar=self.envvar,
                **group_kwargs,
            )
        return option_class(
            self.param_decls,
            type=self.type,
            default=self.default,
            help=self.help,
            is_flag=False,
            multiple=self.multiple,
            required=self.required,
            envvar=self.envvar,
            **group_kwargs,
        )
