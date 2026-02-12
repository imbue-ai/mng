import click


@click.command(name="status")
@click.argument("name", required=False)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show status for all deployed changelings",
)
def status(name: str | None, show_all: bool) -> None:
    """Check the deployment status and recent run history of changeling(s).

    Shows whether the changeling is deployed, when it last ran, and the
    outcome of recent runs (success, failure, PR created, etc).

    Examples:

      changeling status my-fairy

      changeling status --all
    """
    raise NotImplementedError("changeling status is not yet implemented")
