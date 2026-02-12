from typing import Final

from pydantic import Field

from imbue.changelings.primitives import ChangelingTemplateName
from imbue.imbue_common.frozen_model import FrozenModel

CODE_GUARDIAN_DEFAULT_MESSAGE: Final[str] = """\
Identify the most important code-level inconsistencies in this codebase.

Focus on the code itself: look for things that are done in different ways in \
different places, inconsistent variable/function/class naming, and any other \
code-level inconsistencies.

Do NOT worry about docstrings, comments, or documentation -- focus only on the code itself.

Do NOT report issues already covered by an existing FIXME or listed in non_issues.md.

After reviewing the code, think carefully about the most important inconsistencies.

Put them, in order from most important to least important, into a markdown file \
at _tasks/inconsistencies/<date>.md (get the date by running: \
date +%Y-%m-%d-%T | tr : -)

Use this format:

# Inconsistencies identified on <date>

## 1. <Short description>

Description: <detailed description with file names and line numbers>

Recommendation: <recommendation for fixing>

Decision: Accept

Then commit the file and create a PR titled \
"code-guardian: inconsistency report <date>".\
"""


class ChangelingTemplate(FrozenModel):
    """Default configuration values for a built-in changeling template."""

    agent_type: str = Field(description="Default mngr agent type for this template")
    default_message: str = Field(description="Default initial message for the agent")
    description: str = Field(description="Human-readable description of what this template does")


BUILTIN_TEMPLATES: Final[dict[ChangelingTemplateName, ChangelingTemplate]] = {
    ChangelingTemplateName("code-guardian"): ChangelingTemplate(
        agent_type="code-guardian",
        default_message=CODE_GUARDIAN_DEFAULT_MESSAGE,
        description="Creates a markdown report of the largest inconsistencies and problems in the codebase",
    ),
    ChangelingTemplateName("fixme-fairy"): ChangelingTemplate(
        agent_type="claude",
        default_message=(
            "Find all FIXMEs in the codebase, fix as many as you can (one commit per fix), "
            "then create a PR with all the fixes."
        ),
        description="Finds all FIXMEs in the codebase and fixes them, one commit per fix, then creates a PR",
    ),
    ChangelingTemplateName("doc-regent"): ChangelingTemplate(
        agent_type="claude",
        default_message=(
            "Identify places where the documentation and the code disagree. "
            "Produce a markdown report of doc/code inconsistencies and commit it."
        ),
        description="Produces a markdown report of doc/code inconsistencies",
    ),
    ChangelingTemplateName("docstring-scribe"): ChangelingTemplate(
        agent_type="claude",
        default_message=(
            "Identify outdated docstrings in this codebase. "
            "Produce a markdown report of outdated docstrings and commit it."
        ),
        description="Produces a markdown report of outdated docstrings",
    ),
}


def get_template(name: ChangelingTemplateName) -> ChangelingTemplate | None:
    """Get a built-in template by name, or None if not found."""
    return BUILTIN_TEMPLATES.get(name)


def list_template_names() -> list[ChangelingTemplateName]:
    """List all built-in template names."""
    return sorted(BUILTIN_TEMPLATES.keys())
