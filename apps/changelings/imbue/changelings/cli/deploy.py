import click


@click.command(name="deploy")
@click.argument("name", required=False)
@click.option(
    "--all",
    "deploy_all",
    is_flag=True,
    help="Deploy all enabled changelings",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deployed without actually deploying",
)
def deploy(name: str | None, deploy_all: bool, dry_run: bool) -> None:
    """Deploy changeling(s) to Modal as scheduled functions.

    Each changeling becomes a separate Modal App with a cron-scheduled function.
    The deployed app contains the full codebase (including mngr) and runs
    the changeling on its configured schedule.

    Examples:

      changeling deploy my-fairy

      changeling deploy --all

      changeling deploy my-fairy --dry-run
    """
    raise NotImplementedError("changeling deploy is not yet implemented")
