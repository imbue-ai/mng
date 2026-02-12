import pytest

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName
from imbue.changelings.primitives import CronSchedule
from imbue.changelings.primitives import GitRepoUrl


def make_test_definition(
    name: str = "test-fairy",
    template: str = "fixme-fairy",
    schedule: str = "0 3 * * *",
    repo: str = "git@github.com:org/repo.git",
    **kwargs: object,
) -> ChangelingDefinition:
    """Create a ChangelingDefinition for testing with sensible defaults."""
    return ChangelingDefinition(
        name=ChangelingName(name),
        template=ChangelingTemplateName(template),
        schedule=CronSchedule(schedule),
        repo=GitRepoUrl(repo),
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture
def sample_definition() -> ChangelingDefinition:
    return make_test_definition()
