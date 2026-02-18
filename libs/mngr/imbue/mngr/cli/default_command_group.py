import click


class DefaultCommandGroup(click.Group):
    """A click.Group that defaults to a specific subcommand when none is given.

    When no subcommand is provided, or when an unrecognized subcommand is given,
    the arguments are forwarded to the default command.

    Subclasses can set ``_default_command`` to change the default (defaults to
    ``"create"``), and ``_implicit_forward_meta_key`` to store the forwarded
    argument in ``ctx.meta`` (useful for error message context).
    """

    _default_command: str = "create"
    _implicit_forward_meta_key: str | None = None

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args:
            args = [self._default_command]
        return super().parse_args(ctx, args)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        if args:
            cmd = self.get_command(ctx, args[0])
            if cmd is None:
                if self._implicit_forward_meta_key is not None:
                    ctx.meta[self._implicit_forward_meta_key] = args[0]
                return super().resolve_command(ctx, [self._default_command] + args)
        return super().resolve_command(ctx, args)
