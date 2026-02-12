import click


@click.command(name="run")
@click.argument("name")
@click.option(
    "--local",
    is_flag=True,
    help="Run locally instead of on Modal (useful for testing)",
)
def run(name: str, local: bool) -> None:
    """Run a changeling immediately (for testing or one-off execution).

    This bypasses the cron schedule and runs the changeling right now.
    Useful for testing a new changeling before deploying it.

    Examples:

      changeling run my-fairy

      changeling run my-fairy --local
    """
    raise NotImplementedError("changeling run is not yet implemented")
