from __future__ import annotations

from pathlib import Path
from typing import Final

import click
from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mngr import hookimpl
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface

_SKILL_NAME: Final[str] = "code-guardian"

_CODE_GUARDIAN_SKILL_CONTENT: Final[str] = """\
---
name: code-guardian
description: >
  Identify the most important code-level inconsistencies in the codebase and
  produce a structured report. Use when asked to use your primary skill.
---

Important: you are running in a remote sandbox and cannot communicate with the user while you are working through this skill--do NOT ask the user any questions or for any clarifications while compiling the report.  Instead, do your best to complete the task based on the information you have, and make reasonable assumptions if needed.

# Code Guardian: Identify Inconsistencies

Your task is to identify the most important code-level inconsistencies in this codebase.

## Instructions

1. Read through the codebase documentation (CLAUDE.md, README files, style guides, etc.)
   to understand the project's conventions and architecture.
2. Read non_issues.md if it exists -- do NOT report anything listed there.
3. Review the code and identify inconsistencies:
   - Things done in different ways in different places
   - Inconsistent variable/function/class naming
   - Pattern violations and style guide deviations
   - Any other code-level inconsistencies
4. Do NOT worry about docstrings, comments, or documentation (those are covered separately).
5. Do NOT worry about inconsistencies between docs/specs and code (covered separately).
6. Do NOT report issues already covered by an existing FIXME.

## Output

Put the inconsistencies, in order from most important to least important, into a markdown
file at `_tasks/inconsistencies/<date>.md` (create the directory if needed).

Get the date by running: `date +%Y-%m-%d-%T | tr : -`

Use this format:

```markdown
# Inconsistencies identified on <date>

## 1. <Short description>

Description: <detailed description with file names and line numbers>

Recommendation: <recommendation for fixing>

Decision: Accept
```

Then commit the file and either update (if it exists) or create (if it does not exist) a PR titled "code-guardian: inconsistency report".
"""


class CodeGuardianAgentConfig(ClaudeAgentConfig):
    """Config for the code-guardian agent type."""


def _prompt_user_for_skill_install(skill_path: Path) -> bool:
    """Prompt the user to install or update the code-guardian skill."""
    if skill_path.exists():
        logger.info(
            "\nThe code-guardian skill at {} will be updated.\n",
            skill_path,
        )
        return click.confirm("Update the code-guardian skill?", default=True)
    else:
        logger.info(
            "\nThe code-guardian skill will be installed to {}.\n",
            skill_path,
        )
        return click.confirm("Install the code-guardian skill?", default=True)


def _install_skill_locally(mngr_ctx: MngrContext) -> None:
    """Install the code-guardian skill to the local user's ~/.claude/skills/."""
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"

    with log_span("Installing code-guardian skill to {}", skill_path):
        # Skip if the skill is already installed with the same content
        if skill_path.exists() and skill_path.read_text() == _CODE_GUARDIAN_SKILL_CONTENT:
            logger.debug("Code-guardian skill is already up to date at {}", skill_path)
            return

        if mngr_ctx.is_interactive and not mngr_ctx.is_auto_approve:
            if not _prompt_user_for_skill_install(skill_path):
                logger.info("Skipped code-guardian skill installation")
                return

        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_CODE_GUARDIAN_SKILL_CONTENT)
        logger.debug("Installed code-guardian skill to {}", skill_path)


def _install_skill_remotely(host: OnlineHostInterface) -> None:
    """Install the code-guardian skill on a remote host."""
    skill_path = Path(f".claude/skills/{_SKILL_NAME}/SKILL.md")

    with log_span("Installing code-guardian skill on remote host"):
        host.execute_command(
            f"mkdir -p ~/.claude/skills/{_SKILL_NAME}",
            timeout_seconds=10.0,
        )
        host.write_text_file(skill_path, _CODE_GUARDIAN_SKILL_CONTENT)
        logger.debug("Installed code-guardian skill on remote host")


class CodeGuardianAgent(ClaudeAgent):
    """Agent implementation for code-guardian with skill provisioning."""

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mngr_ctx: MngrContext,
    ) -> None:
        """Provision the code-guardian skill and then run standard Claude provisioning."""
        super().provision(host, options, mngr_ctx)

        if host.is_local:
            _install_skill_locally(mngr_ctx)
        else:
            _install_skill_remotely(host)


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the code-guardian agent type."""
    return ("code-guardian", CodeGuardianAgent, CodeGuardianAgentConfig)
