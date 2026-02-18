import click

from imbue.mngr.config.loader import read_default_command


class DefaultCommandGroup(click.Group):
    """A click.Group that defaults to a specific subcommand when none is given.

    When no subcommand is provided, or when an unrecognized subcommand is given,
    the arguments are forwarded to the default command.

    Subclasses can set ``_default_command`` to change the compile-time default
    (defaults to ``"create"``).

    Subclasses can also set ``_config_key`` to enable runtime configuration of
    the default via ``[commands.<config_key>].default_subcommand`` in config
    files.  When ``_config_key`` is set, the config value takes precedence over
    ``_default_command``.  An empty string in config disables defaulting
    entirely (the group shows help / "No such command" instead).
    """

    _default_command: str = "create"
    _config_key: str | None = None

    def _get_default_command(self) -> str:
        """Return the effective default command, consulting config if available."""
        if self._config_key is not None:
            return read_default_command(self._config_key)
        return self._default_command

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            default = self._get_default_command()
            if default:
                args = [default]
        return super().parse_args(ctx, args)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if args:
            cmd = self.get_command(ctx, args[0])
            if cmd is None:
                default = self._get_default_command()
                if default:
                    return super().resolve_command(ctx, [default] + args)
        return super().resolve_command(ctx, args)
