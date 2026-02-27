import click

from imbue.changelings.cli.deploy import deploy
from imbue.changelings.cli.server import server


@click.group()
def cli() -> None:
    """changelings: deploy and manage your own persistent, specialized AI agents."""


cli.add_command(deploy)
cli.add_command(server)
