import json

import click

from imbue.changelings.config import get_default_config_path
from imbue.changelings.config import load_config
from imbue.changelings.errors import ChangelingConfigError


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
@click.option(
    "--config-path",
    default=None,
    type=click.Path(),
    hidden=True,
    help="Path to config file (for testing)",
)
def list_command(show_all: bool, output_format: str, config_path: str | None) -> None:
    """List all registered changelings.

    Shows each changeling's name, template, schedule, target repo, and status.

    Examples:

      changeling list

      changeling list --all

      changeling list --format json
    """
    from pathlib import Path

    config_file = Path(config_path) if config_path else get_default_config_path()

    try:
        config = load_config(config_file)
    except ChangelingConfigError as e:
        raise click.ClickException(str(e))

    changelings = list(config.changeling_by_name.values())
    if not show_all:
        changelings = [c for c in changelings if c.is_enabled]

    if output_format == "json":
        data = [
            {
                "name": str(c.name),
                "template": str(c.template),
                "schedule": str(c.schedule),
                "repo": str(c.repo),
                "branch": c.branch,
                "agent_type": c.agent_type,
                "is_enabled": c.is_enabled,
            }
            for c in changelings
        ]
        click.echo(json.dumps(data, indent=2))
        return

    if not changelings:
        click.echo("No changelings registered.")
        if not show_all:
            click.echo("Use --all to include disabled changelings.")
        return

    # Human-readable table output
    click.echo(f"{'Name':<20} {'Template':<20} {'Schedule':<15} {'Status':<10} {'Repo'}")
    click.echo("-" * 90)
    for c in sorted(changelings, key=lambda x: str(x.name)):
        status = "enabled" if c.is_enabled else "disabled"
        click.echo(f"{str(c.name):<20} {str(c.template):<20} {str(c.schedule):<15} {status:<10} {str(c.repo)}")
