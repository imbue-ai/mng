import click

from imbue.changelings.cli.add import add
from imbue.changelings.cli.list import list_command
from imbue.changelings.cli.remove import remove
from imbue.changelings.cli.run import run
from imbue.changelings.cli.status import status
from imbue.changelings.cli.update import update


@click.group()
@click.version_option(prog_name="changeling", message="%(prog)s %(version)s")
def cli() -> None:
    """Changelings: nightly autonomous agents that maintain your codebase.

    Each changeling is a scheduled agent that performs a specific maintenance
    task -- fixing FIXMEs, improving tests, increasing coverage, writing reports,
    and more. Changelings are deployed as Modal Apps and run on a cron schedule.

    Under the hood, each changeling invokes mngr to create and run an agent
    with the appropriate configuration.
    """


cli.add_command(add)
cli.add_command(remove)
cli.add_command(list_command, name="list")
cli.add_command(update)
cli.add_command(run)
cli.add_command(status)
