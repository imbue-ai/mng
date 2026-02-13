# Integration test for running a changeling locally via the CLI.
#
# This test verifies the end-to-end flow of running a changeling in local mode
# by building the mngr create command and executing it directly.

from pathlib import Path

import pytest

from imbue.changelings.cli.run import _execute_mngr_command
from imbue.changelings.conftest import make_test_changeling
from imbue.changelings.mngr_commands import build_mngr_create_command
from imbue.changelings.mngr_commands import get_agent_name_from_command
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


@pytest.mark.acceptance
@pytest.mark.timeout(120)
def test_run_local_with_cli_args_without_config(tmp_path: Path) -> None:
    """Running locally should create and run a changeling end-to-end.

    Verifies the full flow: builds the mngr create command from a
    ChangelingDefinition, executes it via ConcurrencyGroup, and cleans
    up the created agent with mngr destroy.
    """
    # Use an empty context dir to avoid project-specific pre-command scripts
    context_dir = tmp_path / "mngr-context"
    context_dir.mkdir()

    changeling = make_test_changeling(
        name="test-direct-run",
        agent_type="code-guardian",
        extra_mngr_args=f"--context {context_dir}",
    )
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)
    agent_name = get_agent_name_from_command(cmd)

    try:
        _execute_mngr_command(changeling, cmd)
    finally:
        # Clean up the agent that was created
        with ConcurrencyGroup(name="test-cleanup") as cg:
            cg.run_process_to_completion(
                ["uv", "run", "mngr", "destroy", "--force", agent_name],
                is_checked_after=False,
            )
