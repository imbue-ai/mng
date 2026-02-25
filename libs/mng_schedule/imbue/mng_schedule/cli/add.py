import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mng.api.providers import get_provider_instance
from imbue.mng.cli.common_opts import add_common_options
from imbue.mng.cli.common_opts import setup_command_context
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.providers.modal.instance import ModalProviderInstance
from imbue.mng_schedule.cli.group import add_trigger_options
from imbue.mng_schedule.cli.group import resolve_positional_name
from imbue.mng_schedule.cli.group import schedule
from imbue.mng_schedule.cli.options import ScheduleAddCliOptions
from imbue.mng_schedule.data_types import MngInstallMode
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import ScheduledMngCommand
from imbue.mng_schedule.data_types import VerifyMode
from imbue.mng_schedule.errors import ScheduleDeployError
from imbue.mng_schedule.implementations.local.deploy import deploy_local_schedule
from imbue.mng_schedule.implementations.modal.deploy import deploy_schedule
from imbue.mng_schedule.implementations.modal.deploy import parse_upload_spec


@schedule.command(name="add")
@add_trigger_options
@optgroup.group("Add-specific")
@optgroup.option(
    "--update",
    is_flag=True,
    help="If a schedule with the same name already exists, update it instead of failing.",
)
@add_common_options
@click.pass_context
def schedule_add(ctx: click.Context, **kwargs: Any) -> None:
    """Add a new scheduled trigger.

    Creates a new cron-scheduled trigger that will run the specified mng
    command at the specified interval on the specified provider.

    For local provider: uses the system crontab to schedule the command.
    For modal provider: packages code and deploys a Modal cron function.

    Note that you are responsible for ensuring the correct env vars and files are passed through (this command
    automatically includes user and project settings for mng and any enabled plugins, but you may need to include
    additional env vars or files for your specific remote mng command to run correctly). See the options below for
    how to include env files and uploads in the deployment.

    \b
    Examples:
      mng schedule add --command create --args "--type claude --message 'fix bugs' --in local" --schedule "0 2 * * *" --provider local
      mng schedule add --command create --args "--type claude --message 'fix bugs' --in modal" --schedule "0 2 * * *" --provider modal
    """
    resolve_positional_name(ctx)
    # New schedules default to enabled. The shared options use None so that
    # update can distinguish "not specified" from "explicitly set".
    if ctx.params.get("enabled") is None:
        ctx.params["enabled"] = True
    mng_ctx, _output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="schedule_add",
        command_class=ScheduleAddCliOptions,
    )

    # Validate required options for add
    if opts.command is None:
        raise click.UsageError("--command is required for schedule add")
    if opts.schedule_cron is None:
        raise click.UsageError("--schedule is required for schedule add")
    if opts.provider is None:
        raise click.UsageError("--provider is required for schedule add")

    # Code packaging strategy validation
    if opts.snapshot_id is not None:
        raise NotImplementedError("--snapshot is not yet implemented for schedule add")
    if opts.full_copy:
        raise NotImplementedError("--full-copy is not yet implemented for schedule add")

    # Load the provider instance
    try:
        provider = get_provider_instance(ProviderInstanceName(opts.provider), mng_ctx)
    except MngError as e:
        raise click.ClickException(f"Failed to load provider '{opts.provider}': {e}") from e

    if not isinstance(provider, (LocalProviderInstance, ModalProviderInstance)):
        raise click.ClickException(
            f"Provider '{opts.provider}' (type {type(provider).__name__}) is not supported for schedules. "
            "Supported providers: local, modal."
        )

    # Generate name if not provided
    trigger_name = opts.name if opts.name else f"trigger-{uuid4().hex[:8]}"

    trigger = ScheduleTriggerDefinition(
        name=trigger_name,
        command=ScheduledMngCommand(opts.command.upper()),
        args=opts.args or "",
        schedule_cron=opts.schedule_cron,
        provider=opts.provider,
        is_enabled=opts.enabled if opts.enabled is not None else True,
    )

    if isinstance(provider, LocalProviderInstance):
        _deploy_local(trigger, mng_ctx, opts)
    elif isinstance(provider, ModalProviderInstance):
        _deploy_modal(trigger, mng_ctx, opts, provider)


def _deploy_local(
    trigger: ScheduleTriggerDefinition,
    mng_ctx: MngContext,
    opts: ScheduleAddCliOptions,
) -> None:
    """Deploy a schedule to the local provider using crontab."""
    try:
        deploy_local_schedule(
            trigger,
            mng_ctx,
            sys_argv=sys.argv,
            pass_env=opts.pass_env,
            env_files=tuple(Path(f) for f in opts.env_files),
        )
    except ScheduleDeployError as e:
        raise click.ClickException(str(e)) from e

    logger.info("Schedule '{}' deployed to local crontab", trigger.name)
    click.echo(f"Deployed schedule '{trigger.name}' to local crontab")


def _deploy_modal(
    trigger: ScheduleTriggerDefinition,
    mng_ctx: MngContext,
    opts: ScheduleAddCliOptions,
    provider: ModalProviderInstance,
) -> None:
    """Deploy a schedule to a Modal provider."""
    # Resolve verification mode from CLI option.
    # Only apply verification for create commands (other commands don't produce agents).
    verify_mode = VerifyMode(opts.verify.upper())
    if verify_mode != VerifyMode.NONE and trigger.command != ScheduledMngCommand.CREATE:
        logger.debug(
            "Skipping verification for command '{}': only applicable to 'create' commands",
            trigger.command,
        )
        verify_mode = VerifyMode.NONE

    # Resolve deploy file options (default to True for add)
    include_user_settings = opts.include_user_settings if opts.include_user_settings is not None else True
    include_project_settings = opts.include_project_settings if opts.include_project_settings is not None else True

    # Parse upload specs
    parsed_uploads: list[tuple[Path, str]] = []
    for upload_spec in opts.uploads:
        try:
            parsed_uploads.append(parse_upload_spec(upload_spec))
        except ValueError as e:
            raise click.UsageError(str(e)) from e

    try:
        app_name = deploy_schedule(
            trigger,
            mng_ctx,
            provider=provider,
            verify_mode=verify_mode,
            sys_argv=sys.argv,
            include_user_settings=include_user_settings,
            include_project_settings=include_project_settings,
            pass_env=opts.pass_env,
            env_files=tuple(Path(f) for f in opts.env_files),
            uploads=parsed_uploads,
            mng_install_mode=MngInstallMode(opts.mng_install_mode.upper()),
        )
    except ScheduleDeployError as e:
        raise click.ClickException(str(e)) from e

    logger.info("Schedule '{}' deployed as Modal app '{}'", trigger.name, app_name)
    click.echo(f"Deployed schedule '{trigger.name}' as Modal app '{app_name}'")
