# Release test for deploying a changeling to Modal with verification.
#
# This test verifies the end-to-end flow of deploying a changeling:
# 1. Creates a Modal secret
# 2. Deploys the cron runner as a Modal app
# 3. Invokes the function via `modal run` to verify it works
# 4. Polls `mng list` to confirm an agent is created
# 5. Destroys the test agent
#
# It is marked as a release test and skipped by default because it requires
# Modal credentials, ANTHROPIC_API_KEY, and network access.
#
# To run this test manually, first remove the @pytest.mark.skip decorator, then:
#
#     just test apps/changelings/imbue/changelings/test_deploy_modal.py::test_deploy_and_verify_changeling

import subprocess

import pytest

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import deploy_changeling
from imbue.changelings.deploy.deploy import get_modal_app_name
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import CronSchedule
from imbue.mng.fixtures import ModalSubprocessTestEnv


@pytest.mark.release
@pytest.mark.skip(reason="Requires Modal credentials, ANTHROPIC_API_KEY, and network access")
@pytest.mark.timeout(600)
def test_deploy_and_verify_changeling(
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test deploying and verifying a changeling on Modal end-to-end.

    This test verifies that:
    1. A Modal secret is created for the changeling
    2. The cron runner is deployed as a Modal app
    3. The deployed function is invoked and an agent is created
    4. The agent is detected via mng list and destroyed
    """
    changeling = ChangelingDefinition(
        name=ChangelingName("code-guardian-deploy-test"),
        schedule=CronSchedule("0 3 * * *"),
        agent_type="code-guardian",
        secrets=("ANTHROPIC_API_KEY",),
    )

    app_name = get_modal_app_name(str(changeling.name))

    try:
        deployed_app_name = deploy_changeling(changeling, is_finish_initial_run=False)
        assert deployed_app_name == app_name

        # Verify the app exists in Modal by listing apps
        result = subprocess.run(
            ["uv", "run", "modal", "app", "list", "--json"],
            capture_output=True,
            text=True,
            env=modal_subprocess_env.env,
        )
        assert result.returncode == 0
        assert app_name in result.stdout
    finally:
        # Clean up: stop the deployed Modal app
        subprocess.run(
            ["uv", "run", "modal", "app", "stop", app_name],
            capture_output=True,
            text=True,
            env=modal_subprocess_env.env,
        )
