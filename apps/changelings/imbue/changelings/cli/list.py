import click


@click.command(name="list")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show disabled changelings as well",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="Output format [default: human]",
)
def list_command(show_all: bool, output_format: str) -> None:
    """List all registered changelings.

    Shows each changeling's name, agent type, schedule, target repo, and status.

    Examples:

      changeling list

      changeling list --all

      changeling list --format json
    """
    raise NotImplementedError("changeling list is not yet implemented")
