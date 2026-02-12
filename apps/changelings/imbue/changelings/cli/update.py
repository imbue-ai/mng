import click


@click.command(name="update")
@click.argument("name", required=False)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deployed without actually deploying",
)
def update(name: str | None, dry_run: bool) -> None:
    """Just an alias for `changeling add --update`"""
    raise NotImplementedError("changeling update is not yet implemented")
