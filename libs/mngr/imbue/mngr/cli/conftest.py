import pytest

from imbue.mngr.cli.connect import ConnectCliOptions
from imbue.mngr.cli.create import CreateCliOptions


@pytest.fixture
def default_create_cli_opts() -> CreateCliOptions:
    """Baseline CreateCliOptions with sensible defaults for all fields.

    Tests use .model_copy_update() with to_update_dict() to override only the fields
    relevant to each test case.
    """
    return CreateCliOptions(
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
        positional_name=None,
        positional_agent_type=None,
        agent_args=(),
        template=(),
        agent_type=None,
        reuse=False,
        connect=True,
        await_ready=None,
        await_agent_stopped=None,
        copy_work_dir=None,
        ensure_clean=True,
        snapshot_source=None,
        name=None,
        name_style="english",
        agent_command=None,
        add_command=(),
        user=None,
        source=None,
        source_agent=None,
        source_host=None,
        source_path=None,
        target=None,
        target_path=None,
        in_place=False,
        copy_source=False,
        clone=False,
        worktree=False,
        rsync=None,
        rsync_args=None,
        include_git=True,
        include_unclean=None,
        include_gitignored=False,
        base_branch=None,
        new_branch="",
        new_branch_prefix="mngr/",
        depth=None,
        shallow_since=None,
        agent_env=(),
        agent_env_file=(),
        pass_agent_env=(),
        host=None,
        new_host=None,
        host_name=None,
        host_name_style="astronomy",
        tag=(),
        project=None,
        host_env=(),
        host_env_file=(),
        pass_host_env=(),
        known_host=(),
        snapshot=None,
        build_arg=(),
        build_args=None,
        start_arg=(),
        start_args=None,
        reconnect=True,
        interactive=None,
        message=None,
        message_file=None,
        edit_message=False,
        resume_message=None,
        resume_message_file=None,
        retry=3,
        retry_delay="5s",
        attach_command=None,
        idle_timeout=None,
        idle_mode=None,
        activity_sources=None,
        start_on_boot=None,
        grant=(),
        user_command=(),
        sudo_command=(),
        upload_file=(),
        append_to_file=(),
        prepend_to_file=(),
        create_directory=(),
        ready_timeout=10.0,
    )


@pytest.fixture
def default_connect_cli_opts() -> ConnectCliOptions:
    """Baseline ConnectCliOptions with sensible defaults for all fields.

    Tests use .model_copy_update() with to_update() to override only the fields
    relevant to each test case.
    """
    return ConnectCliOptions(
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
        agent=None,
        start=True,
        reconnect=True,
        message=None,
        message_file=None,
        ready_timeout=10.0,
        retry=3,
        retry_delay="5s",
        attach_command=None,
        allow_unknown_host=False,
    )
