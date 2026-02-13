# Shared click options and helpers for CLI commands that accept ChangelingDefinition fields.

from collections.abc import Callable

import click

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl


def _parse_key_value_pairs(pairs: tuple[str, ...]) -> dict[str, str]:
    """Parse a tuple of KEY=VALUE strings into a dict."""
    result: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise click.BadParameter(f"Expected KEY=VALUE format, got: {pair}")
        key, value = pair.split("=", 1)
        result[key] = value
    return result


def changeling_definition_options(f: Callable) -> Callable:
    """Decorator that adds all ChangelingDefinition-related click options to a command."""
    decorators = [
        click.option(
            "--schedule",
            default=None,
            help="Cron expression for when this changeling runs (e.g., '0 3 * * *')",
        ),
        click.option(
            "--repo",
            default=None,
            help="Git repository URL to operate on",
        ),
        click.option(
            "--branch",
            default=None,
            help="Base branch to work from",
        ),
        click.option(
            "--message",
            default=None,
            help="Initial message to send to the agent",
        ),
        click.option(
            "--agent-type",
            default=None,
            help="The mngr agent type to use",
        ),
        click.option(
            "--secret",
            "secrets",
            multiple=True,
            help="Secret env var name to forward (repeatable)",
        ),
        click.option(
            "--env-var",
            "env_vars",
            multiple=True,
            help="Environment variable KEY=VALUE to set (repeatable)",
        ),
        click.option(
            "--extra-mngr-args",
            default=None,
            help="Extra arguments to pass to mngr create (as a single string)",
        ),
        click.option(
            "-o",
            "--option",
            "mngr_options",
            multiple=True,
            help="Custom mngr option KEY=VALUE (repeatable)",
        ),
        click.option(
            "--enabled/--disabled",
            default=None,
            help="Whether this changeling should be active",
        ),
    ]
    for decorator in reversed(decorators):
        f = decorator(f)
    return f


def build_definition_from_cli(
    name: str,
    schedule: str | None,
    repo: str | None,
    branch: str | None,
    message: str | None,
    agent_type: str | None,
    secrets: tuple[str, ...],
    env_vars: tuple[str, ...],
    extra_mngr_args: str | None,
    mngr_options: tuple[str, ...],
    enabled: bool | None,
    # If provided, CLI args are merged onto this base definition
    base: ChangelingDefinition | None,
) -> ChangelingDefinition:
    """Build a ChangelingDefinition from CLI arguments, optionally merging onto a base."""
    parsed_env_vars = _parse_key_value_pairs(env_vars) if env_vars else None
    parsed_mngr_options = _parse_key_value_pairs(mngr_options) if mngr_options else None

    if base is not None:
        # Merge CLI args onto base, keeping base values for anything not specified
        return ChangelingDefinition(
            name=base.name,
            schedule=CronSchedule(schedule) if schedule is not None else base.schedule,
            repo=GitRepoUrl(repo) if repo is not None else base.repo,
            branch=branch if branch is not None else base.branch,
            initial_message=message if message is not None else base.initial_message,
            agent_type=agent_type if agent_type is not None else base.agent_type,
            secrets=secrets if secrets else base.secrets,
            env_vars=parsed_env_vars if parsed_env_vars is not None else base.env_vars,
            extra_mngr_args=extra_mngr_args if extra_mngr_args is not None else base.extra_mngr_args,
            mngr_options=parsed_mngr_options if parsed_mngr_options is not None else base.mngr_options,
            is_enabled=enabled if enabled is not None else base.is_enabled,
        )

    # Create from scratch, relying on model defaults for unspecified fields
    kwargs: dict = {"name": ChangelingName(name)}
    if schedule is not None:
        kwargs["schedule"] = CronSchedule(schedule)
    if repo is not None:
        kwargs["repo"] = GitRepoUrl(repo)
    if branch is not None:
        kwargs["branch"] = branch
    if message is not None:
        kwargs["initial_message"] = message
    # Default agent_type to the changeling name (per design.md)
    kwargs["agent_type"] = agent_type if agent_type is not None else name
    if secrets:
        kwargs["secrets"] = secrets
    if parsed_env_vars:
        kwargs["env_vars"] = parsed_env_vars
    if extra_mngr_args is not None:
        kwargs["extra_mngr_args"] = extra_mngr_args
    if parsed_mngr_options:
        kwargs["mngr_options"] = parsed_mngr_options
    if enabled is not None:
        kwargs["is_enabled"] = enabled
    return ChangelingDefinition(**kwargs)
