from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName


def make_test_changeling(
    name: str = "test-changeling",
    template: str = "code-guardian",
    agent_type: str = "code-guardian",
    branch: str = "main",
    initial_message: str = DEFAULT_INITIAL_MESSAGE,
    extra_mngr_args: str = "",
    env_vars: dict[str, str] | None = None,
    secrets: tuple[str, ...] | None = None,
) -> ChangelingDefinition:
    """Create a ChangelingDefinition for testing."""
    kwargs: dict = {
        "name": ChangelingName(name),
        "template": ChangelingTemplateName(template),
        "agent_type": agent_type,
        "branch": branch,
        "initial_message": initial_message,
        "extra_mngr_args": extra_mngr_args,
        "env_vars": env_vars or {},
    }
    if secrets is not None:
        kwargs["secrets"] = secrets
    return ChangelingDefinition(**kwargs)
