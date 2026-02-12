import click


@click.command(name="remove")
@click.argument("name")
@click.option(
    "--force",
    is_flag=True,
    help="Skip confirmation and also undeploy from Modal if deployed",
)
def remove(name: str, force: bool) -> None:
    """Remove a registered changeling.

    This removes the changeling from the local configuration. If the changeling
    is currently deployed to Modal, use --force to also undeploy it.

    Examples:

      changeling remove my-fairy

      changeling remove my-fairy --force
    """
    raise NotImplementedError("changeling remove is not yet implemented")
