import click


@click.command(name="add")
@click.argument("name")
@click.option(
    "--template",
    required=True,
    help="Built-in template to use (e.g., fixme-fairy, test-troll, coverage-hunter)",
)
@click.option(
    "--repo",
    required=True,
    help="Git repository URL to operate on",
)
@click.option(
    "--schedule",
    required=True,
    help="Cron expression for when this changeling runs (e.g., '0 3 * * *' for 3am daily)",
)
@click.option(
    "--branch",
    default="main",
    help="Base branch to work from [default: main]",
)
@click.option(
    "--message",
    default=None,
    help="Custom initial message to send to the agent (overrides template default)",
)
@click.option(
    "--agent-type",
    default="claude",
    help="The mngr agent type to use [default: claude]",
)
@click.option(
    "--enabled/--disabled",
    default=True,
    help="Whether this changeling should be active immediately [default: enabled]",
)
def add(
    name: str,
    template: str,
    repo: str,
    schedule: str,
    branch: str,
    message: str | None,
    agent_type: str,
    enabled: bool,
) -> None:
    """Register a new changeling.

    A changeling is an autonomous agent that runs on a schedule to perform
    maintenance tasks on your codebase (fixing FIXMEs, improving tests, etc).

    Examples:

      changeling add my-fairy --template fixme-fairy --repo git@github.com:org/repo.git --schedule "0 3 * * *"

      changeling add test-bot --template test-troll --repo git@github.com:org/repo.git --schedule "0 4 * * 1"
    """
    raise NotImplementedError("changeling add is not yet implemented")
