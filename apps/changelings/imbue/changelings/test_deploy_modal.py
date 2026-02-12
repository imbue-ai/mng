"""Release test for deploying a changeling to Modal.

This test verifies the end-to-end flow of deploying a code-guardian changeling
as a cron-scheduled Modal Function. It is marked as a release test and skipped
by default because it requires Modal credentials and network access.

To run this test manually, first remove the @pytest.mark.skip decorator, then:

    just test apps/changelings/imbue/changelings/test_deploy_modal.py::test_deploy_code_guardian_changeling_to_modal
"""

import subprocess

import pytest

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.deploy.deploy import deploy_changeling
from imbue.changelings.deploy.deploy import get_modal_app_name
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.primitives import CronSchedule
from imbue.mngr.conftest import ModalSubprocessTestEnv


@pytest.mark.release
@pytest.mark.skip(reason="Requires Modal credentials and network access")
@pytest.mark.timeout(600)
def test_deploy_code_guardian_changeling_to_modal(
    modal_subprocess_env: ModalSubprocessTestEnv,
) -> None:
    """Test deploying a code-guardian changeling to Modal end-to-end.

    This test verifies that:
    1. A Modal secret is created for the changeling
    2. The cron runner is deployed as a Modal app
    3. The deployed app exists and can be queried
    """
    changeling = ChangelingDefinition(
        name=ChangelingName("code-guardian-deploy-test"),
        template=ChangelingTemplateName("code-guardian"),
        schedule=CronSchedule("0 3 * * *"),
        agent_type="code-guardian",
        secrets=("ANTHROPIC_API_KEY",),
    )

    app_name = get_modal_app_name(str(changeling.name))

    try:
        deployed_app_name = deploy_changeling(changeling)
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
