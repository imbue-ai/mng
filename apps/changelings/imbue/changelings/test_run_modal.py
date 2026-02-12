"""Release test for running a changeling on Modal.

This test verifies the end-to-end flow of running a code-guardian changeling
on Modal. It is marked as a release test and skipped by default because it
requires Modal credentials, a valid ANTHROPIC_API_KEY, and network access.

To run this test manually:

    just test apps/changelings/imbue/changelings/test_run_modal.py::test_run_code_guardian_changeling_on_modal
"""

import subprocess

import pytest

from imbue.mngr.conftest import ModalSubprocessTestEnv
from imbue.mngr.utils.testing import get_short_random_string


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
    agent_name = f"changeling-test-{get_short_random_string()}"

    # Run mngr create with code-guardian agent type on Modal.
    # This is the exact command that `changeling run` would build,
    # minus the changeling-specific wrapping.
    result = subprocess.run(
        [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            "code-guardian",
            "--in",
            "modal",
            "--no-connect",
            "--await-agent-stopped",
            "--no-ensure-clean",
            "--tag",
            "CREATOR=changeling",
            "--tag",
            "CHANGELING=code-guardian-test",
            "--pass-host-env",
            "ANTHROPIC_API_KEY",
            "--message",
            "Please use your primary skill",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env=modal_subprocess_env.env,
    )

    assert result.returncode == 0, (
        f"mngr create on Modal failed with code {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
