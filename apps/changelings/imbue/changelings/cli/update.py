import click
from loguru import logger

from imbue.changelings.deployment.local import UpdateResult
from imbue.changelings.deployment.local import update_local
from imbue.changelings.errors import ChangelingError
from imbue.changelings.primitives import AgentName
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


def _run_update(
    agent_name: AgentName,
    do_snapshot: bool,
    do_push: bool,
    do_provision: bool,
) -> UpdateResult:
    """Run the update process and return the result.

    Raises ChangelingError if any step fails.
    """
    cg = ConcurrencyGroup(name="changeling-update")
    update_error: ChangelingError | None = None
    with cg:
        try:
            result = update_local(
                agent_name=agent_name,
                do_snapshot=do_snapshot,
                do_push=do_push,
                do_provision=do_provision,
                concurrency_group=cg,
            )
        except ChangelingError as e:
            update_error = e

    if update_error is not None:
        raise update_error

    return result


def _print_result(result: UpdateResult) -> None:
    """Print the update result summary."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("Changeling updated successfully")
    logger.info("=" * 60)
    logger.info("")
    logger.info("  Agent name: {}", result.agent_name)
    logger.info("")
    steps: list[str] = []
    if result.did_snapshot:
        steps.append("snapshot")
    steps.append("stop")
    if result.did_push:
        steps.append("push")
    if result.did_provision:
        steps.append("provision")
    steps.append("start")
    logger.info("  Steps completed: {}", " -> ".join(steps))
    logger.info("=" * 60)


@click.command()
@click.argument("agent_name")
@click.option(
    "--snapshot/--no-snapshot",
    default=True,
    show_default=True,
    help="Create a snapshot before updating (for easy rollback)",
)
@click.option(
    "--push/--no-push",
    default=True,
    show_default=True,
    help="Push new code/content to the agent",
)
@click.option(
    "--provision/--no-provision",
    default=True,
    show_default=True,
    help="Re-run provisioning to sync config and auth",
)
def update(
    agent_name: str,
    snapshot: bool,
    push: bool,
    provision: bool,
) -> None:
    """Update an existing changeling by redeploying into it.

    AGENT_NAME is the name of the changeling to update.

    By default, the update process:

    \b
    1. Creates a snapshot (for easy rollback)
    2. Stops the agent
    3. Pushes new code/content
    4. Re-runs provisioning (to sync config and auth)
    5. Starts the agent

    Use --no-snapshot, --no-push, or --no-provision to skip individual steps.
    Stop and start are always performed.

    Example:

    \b
        changeling update my-agent
        changeling update my-agent --no-snapshot
        changeling update my-agent --no-push --no-provision
    """
    logger.info("Updating changeling '{}'...", agent_name)

    result = _run_update(
        agent_name=AgentName(agent_name),
        do_snapshot=snapshot,
        do_push=push,
        do_provision=provision,
    )

    _print_result(result)
