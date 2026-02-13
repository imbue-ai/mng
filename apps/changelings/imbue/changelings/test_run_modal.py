# Release test for running a changeling on Modal.
#
# This test verifies the end-to-end flow of running a code-guardian changeling
# on Modal. It is marked as a release test and skipped by default because it
# requires Modal credentials, a valid ANTHROPIC_API_KEY, and network access.
#
# To run this test manually, first remove the @pytest.mark.skip decorator, then:
#
#     just test apps/changelings/imbue/changelings/test_run_modal.py::test_run_code_guardian_changeling_on_modal

import pytest

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.mngr_commands import build_mngr_create_command
from imbue.changelings.mngr_commands import get_agent_name_from_command
from imbue.changelings.mngr_commands import write_secrets_env_file
from imbue.changelings.primitives import ChangelingName
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.conftest import ModalSubprocessTestEnv


@pytest.mark.release
@pytest.mark.skip(reason="Requires Modal credentials, ANTHROPIC_API_KEY, and a target repo")
@pytest.mark.timeout(600)
def test_run_code_guardian_changeling_on_modal(
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test creating and running a code-guardian changeling on Modal end-to-end.

    This test verifies that:
    1. The mngr create command is constructed correctly for Modal
    2. A Modal sandbox is created and provisioned
    3. The code-guardian agent type is resolved and provisioned
    4. The agent runs and completes (or at least starts successfully)
    """
    changeling = ChangelingDefinition(
        name=ChangelingName("code-guardian-test"),
        agent_type="code-guardian",
    )

    # Write secrets to a temp env file (same flow as _run_changeling_on_modal)
    env_file_path = write_secrets_env_file(changeling)
    try:
        # Build the command (already starts with "uv run mngr create ...")
        cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=env_file_path)
        agent_name = get_agent_name_from_command(cmd)

        with ConcurrencyGroup(name="test-modal-run") as cg:
            result = cg.run_process_to_completion(
                cmd,
                timeout=600.0,
                env=modal_subprocess_env.env,
                is_checked_after=False,
            )

        assert result.returncode == 0, (
            f"mngr create on Modal failed with code {result.returncode}.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    finally:
        env_file_path.unlink(missing_ok=True)
        # Clean up the agent
        with ConcurrencyGroup(name="test-cleanup") as cg:
            cg.run_process_to_completion(
                ["uv", "run", "mngr", "destroy", "--force", agent_name],
                is_checked_after=False,
            )
