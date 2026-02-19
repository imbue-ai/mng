# Integration test for running a changeling locally via the CLI.
#
# This test verifies the end-to-end flow of running a changeling in local mode
# by building the mng create command and executing it directly.

from pathlib import Path

import pytest

from imbue.changelings.cli.run import _execute_mng_command
from imbue.changelings.conftest import make_test_changeling
from imbue.changelings.mng_commands import build_mng_create_command
from imbue.changelings.mng_commands import get_agent_name_from_command
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup


@pytest.mark.release
@pytest.mark.skip(
    reason="Requires claude locally, not installed in CI, and even if installed, has annoying dialogs to click through"
)
@pytest.mark.timeout(120)
def test_run_local_with_cli_args_without_config(tmp_path: Path) -> None:
    """Running locally should create and run a changeling end-to-end.

    Verifies the full flow: builds the mng create command from a
    ChangelingDefinition, executes it via ConcurrencyGroup, and cleans
    up the created agent with mng destroy.
    """
    # Use an empty context dir to avoid project-specific pre-command scripts
    context_dir = tmp_path / "mng-context"
    context_dir.mkdir()

    changeling = make_test_changeling(
        name="test-direct-run",
        agent_type="code-guardian",
        extra_mng_args=f"--context {context_dir}",
    )
    cmd = build_mng_create_command(changeling, is_modal=False, env_file_path=None)
    agent_name = get_agent_name_from_command(cmd)

    try:
        _execute_mng_command(changeling, cmd)
    finally:
        # Clean up the agent that was created
        with ConcurrencyGroup(name="test-cleanup") as cg:
            cg.run_process_to_completion(
                ["uv", "run", "mng", "destroy", "--force", agent_name],
                is_checked_after=False,
            )
