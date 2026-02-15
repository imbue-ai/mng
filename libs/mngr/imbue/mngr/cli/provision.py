from pathlib import Path
from typing import Any
from typing import assert_never

import click
from click_option_group import optgroup
from loguru import logger

from imbue.mngr.api.provision import provision_agent
from imbue.mngr.cli.agent_utils import find_agent_for_command
from imbue.mngr.cli.common_opts import CommonCliOptions
from imbue.mngr.cli.common_opts import add_common_options
from imbue.mngr.cli.common_opts import setup_command_context
from imbue.mngr.cli.env_utils import resolve_env_vars
from imbue.mngr.cli.help_formatter import CommandHelpMetadata
from imbue.mngr.cli.help_formatter import add_pager_help_option
from imbue.mngr.cli.help_formatter import register_help_metadata
from imbue.mngr.cli.output_helpers import emit_event
from imbue.mngr.cli.output_helpers import emit_final_json
from imbue.mngr.config.data_types import OutputOptions
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.host import AgentEnvironmentOptions
from imbue.mngr.interfaces.host import AgentProvisioningOptions
from imbue.mngr.interfaces.host import FileModificationSpec
from imbue.mngr.interfaces.host import UploadFileSpec
from imbue.mngr.primitives import OutputFormat


class ProvisionCliOptions(CommonCliOptions):
    """Options passed from the CLI to the provision command."""

    agent: str | None
    agent_option: str | None
    host: str | None
    # Behavior options
    bootstrap: str | None
    destroy_on_fail: bool
    # Provisioning options
    user_command: tuple[str, ...]
    sudo_command: tuple[str, ...]
    upload_file: tuple[str, ...]
    append_to_file: tuple[str, ...]
    prepend_to_file: tuple[str, ...]
    create_directory: tuple[str, ...]
    # Environment options
    agent_env: tuple[str, ...]
    agent_env_file: tuple[str, ...]
    pass_agent_env: tuple[str, ...]


def _output_result(agent_name: str, output_opts: OutputOptions) -> None:
    """Output the final result."""
    result_data = {"agent": agent_name, "provisioned": True}
    match output_opts.output_format:
        case OutputFormat.JSON:
            emit_final_json(result_data)
        case OutputFormat.JSONL:
            emit_event("provision_result", result_data, OutputFormat.JSONL)
        case OutputFormat.HUMAN:
            pass
        case _ as unreachable:
            assert_never(unreachable)


@click.command(name="provision")
@click.argument("agent", required=False, default=None)
@optgroup.group("Target Selection")
@optgroup.option(
    "--agent",
    "agent_option",
    help="Agent name or ID to provision (alternative to positional argument)",
)
@optgroup.option(
    "--host",
    help="Filter by host name or ID [future]",
)
@optgroup.group("Behavior")
@optgroup.option(
    "--bootstrap",
    type=click.Choice(["yes", "warn", "no"], case_sensitive=False),
    default=None,
    help="Auto-install missing required tools: yes, warn (install with warning), or no [default: warn on remote, no on local] [future]",
)
@optgroup.option(
    "--destroy-on-fail/--no-destroy-on-fail",
    "destroy_on_fail",
    default=False,
    help="Destroy the host if provisioning fails [future]",
)
@optgroup.group("Agent Provisioning")
@optgroup.option(
    "--user-command",
    "user_command",
    multiple=True,
    help="Run custom shell command during provisioning [repeatable]",
)
@optgroup.option(
    "--sudo-command",
    "sudo_command",
    multiple=True,
    help="Run custom shell command as root during provisioning [repeatable]",
)
@optgroup.option(
    "--upload-file",
    "upload_file",
    multiple=True,
    help="Upload LOCAL:REMOTE file pair [repeatable]",
)
@optgroup.option(
    "--append-to-file",
    "append_to_file",
    multiple=True,
    help="Append REMOTE:TEXT to file [repeatable]",
)
@optgroup.option(
    "--prepend-to-file",
    "prepend_to_file",
    multiple=True,
    help="Prepend REMOTE:TEXT to file [repeatable]",
)
@optgroup.option(
    "--create-directory",
    "create_directory",
    multiple=True,
    help="Create directory on remote [repeatable]",
)
@optgroup.group("Agent Environment Variables")
@optgroup.option(
    "--env",
    "--agent-env",
    "agent_env",
    multiple=True,
    help="Set environment variable KEY=VALUE",
)
@optgroup.option(
    "--env-file",
    "--agent-env-file",
    "agent_env_file",
    type=click.Path(exists=True),
    multiple=True,
    help="Load env file",
)
@optgroup.option(
    "--pass-env",
    "--pass-agent-env",
    "pass_agent_env",
    multiple=True,
    help="Forward variable from shell",
)
@add_common_options
@click.pass_context
def provision(ctx: click.Context, **kwargs: Any) -> None:
    """Re-run provisioning on an existing agent.

    This re-runs the provisioning steps (plugin lifecycle hooks, file transfers,
    user commands, env vars) on an agent that has already been created. Useful for
    syncing config, auth, and installing additional packages. Most provisioning
    steps are specified via plugins, but custom steps can also be defined using the
    options below.

    The agent's existing environment variables are preserved. New env vars from
    --env, --env-file, and --pass-env override existing ones with the same key.

    The command runs regardless of whether the agent is running or stopped.
    Provisioning steps are designed to be idempotent. Note that provisioning a
    running agent may cause brief disruption if config files are overwritten
    while the agent is actively reading them.

    Provisioning is done per agent, but changes are visible to other agents on the
    same host. Be careful to avoid conflicts when provisioning multiple agents on
    the same host.

    \b
    Alias: prov

    \b
    Examples:

      mngr provision my-agent

      mngr provision my-agent --user-command "pip install pandas"

      mngr provision my-agent --env "NEW_VAR=value"

      mngr provision my-agent --upload-file ./config.json:/app/config.json
    """
    mngr_ctx, output_opts, opts = setup_command_context(
        ctx=ctx,
        command_name="provision",
        command_class=ProvisionCliOptions,
    )
    logger.debug("Started provision command")

    # Check for unsupported [future] options
    if opts.host is not None:
        raise NotImplementedError("--host is not implemented yet")
    if opts.bootstrap is not None:
        raise NotImplementedError("--bootstrap is not implemented yet")
    if opts.destroy_on_fail:
        raise NotImplementedError("--destroy-on-fail is not implemented yet")

    # Resolve agent identifier from positional argument or --agent option
    agent_identifier: str | None
    if opts.agent is not None and opts.agent_option is not None:
        raise UserInputError("Cannot specify both positional agent and --agent option")
    elif opts.agent is not None:
        agent_identifier = opts.agent
    elif opts.agent_option is not None:
        agent_identifier = opts.agent_option
    else:
        agent_identifier = None

    # Find the agent (start the host if needed, but don't require the agent to be running)
    result = find_agent_for_command(
        mngr_ctx=mngr_ctx,
        agent_identifier=agent_identifier,
        command_usage="provision",
        host_filter=None,
        is_start_desired=True,
        skip_agent_state_check=True,
    )
    if result is None:
        logger.info("No agent selected")
        return

    agent, host = result

    # Parse provisioning options
    provisioning = AgentProvisioningOptions(
        user_commands=opts.user_command,
        sudo_commands=opts.sudo_command,
        upload_files=tuple(UploadFileSpec.from_string(f) for f in opts.upload_file),
        append_to_files=tuple(FileModificationSpec.from_string(f) for f in opts.append_to_file),
        prepend_to_files=tuple(FileModificationSpec.from_string(f) for f in opts.prepend_to_file),
        create_directories=tuple(Path(d) for d in opts.create_directory),
    )

    # Parse environment options
    env_vars = resolve_env_vars(opts.pass_agent_env, opts.agent_env)
    env_files = tuple(Path(f) for f in opts.agent_env_file)

    environment = AgentEnvironmentOptions(
        env_vars=env_vars,
        env_files=env_files,
    )

    # Call the API
    provision_agent(
        agent=agent,
        host=host,
        provisioning=provisioning,
        environment=environment,
        mngr_ctx=mngr_ctx,
    )

    # Output result
    _output_result(str(agent.name), output_opts)


# Register help metadata for git-style help formatting
_PROVISION_HELP_METADATA = CommandHelpMetadata(
    name="mngr-provision",
    one_line_description="Re-run provisioning on an existing agent",
    synopsis="mngr [provision|prov] [AGENT] [--agent <AGENT>] [--user-command <CMD>] [--upload-file <LOCAL:REMOTE>] [--env <KEY=VALUE>]",
    description="""Re-run provisioning on an existing agent.

This re-runs the provisioning steps (plugin lifecycle hooks, file transfers,
user commands, env vars) on an agent that has already been created. Useful for
syncing configuration, authentication, and installing additional packages. Most
provisioning steps are specified via plugins, but custom steps can also be
defined using the options below.

The agent's existing environment variables are preserved. New env vars from
--env, --env-file, and --pass-env override existing ones with the same key.

The command runs regardless of whether the agent is running or stopped.
Provisioning steps are designed to be idempotent. Note that provisioning a
running agent may cause brief disruption if config files are overwritten
while the agent is actively reading them. Consider stopping the agent first
if that is a concern.

Provisioning is done per agent, but changes are visible to other agents on the
same host. Be careful to avoid conflicts when provisioning multiple agents on
the same host.""",
    aliases=("prov",),
    arguments_description="- `AGENT`: Agent name or ID to provision",
    examples=(
        ("Re-provision an agent", "mngr provision my-agent"),
        ("Install a package", "mngr provision my-agent --user-command 'pip install pandas'"),
        ("Upload a config file", "mngr provision my-agent --upload-file ./config.json:/app/config.json"),
        ("Set an environment variable", "mngr provision my-agent --env 'API_KEY=secret'"),
        ("Run a root command", "mngr provision my-agent --sudo-command 'apt-get install -y ffmpeg'"),
    ),
    see_also=(
        ("create", "Create and run an agent"),
        ("connect", "Connect to an agent"),
        ("list", "List existing agents"),
    ),
)

register_help_metadata("provision", _PROVISION_HELP_METADATA)
for alias in _PROVISION_HELP_METADATA.aliases:
    register_help_metadata(alias, _PROVISION_HELP_METADATA)

add_pager_help_option(provision)
