from __future__ import annotations

from pathlib import Path
from typing import Final

import click
from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mng import hookimpl
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.config.data_types import AgentTypeConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.agent import AgentInterface
from imbue.mng.interfaces.host import CreateAgentOptions
from imbue.mng.interfaces.host import OnlineHostInterface

_SKILL_NAME: Final[str] = "fixme-fairy"

_FIXME_FAIRY_SKILL_CONTENT: Final[str] = """\
---
name: fixme-fairy
description: >
  Find and fix a random FIXME in the codebase. Use when asked to use your
  primary skill.
---

Important: you are running in a remote sandbox and cannot communicate with \
the user while you are working through this skill--do NOT ask the user any \
questions or for any clarifications while working. Instead, do your best to \
complete the task based on the information you have, and make reasonable \
assumptions if needed.

# Fixme Fairy: Fix a Random FIXME

Your task is to find and fix ONE random FIXME in this codebase.

## FIXME Format

FIXMEs in this codebase follow this format:

```python
# FIXME(priority)[attempts=N]: (description)
#  (optional additional context)
```

where `description` is a short description of what needs to be fixed, and \
`N` is the number of prior attempts made to fix it (if any).
If there have been no prior attempts, the `[attempts=N]` part may be omitted.
The priority is simply an integer, with 0 being the highest priority. \
Priority may or may not be present.
If not present, assume priority=3.

## Step 1: Find a Random FIXME

Run this bash command to select a random FIXME, prioritized by severity:

```bash
( grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME0:' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME0[attempts=1]' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME1:' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME1[attempts=1]' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME2:' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME2[attempts=1]' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME3:' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
-P '# FIXME3[attempts=1]' -r . || \\
  grep --exclude-dir=htmlcov --exclude-dir=.venv --exclude-dir=.git \
--exclude-dir=node_modules --exclude='random_fixme.sh' \
--exclude='*.md' -P '# FIXME:' -r . ) | shuf -n 1
```

If no lines are returned, there are no remaining FIXMEs. In that case, \
report that there are no FIXMEs left and skip the rest of this process.

## Step 2: Understand the FIXME

1. Find that FIXME and read the surrounding context (the optional additional \
context lines below the FIXME line may be important).
2. Gather all the context for the library that contains the FIXME (read \
CLAUDE.md, docs, style guides, README files, etc.).
3. Think carefully about how best to fix the FIXME.

## Step 3: Fix the FIXME

1. Implement the fix.
2. Run the tests: `uv run pytest`
3. Fix any test failures until all tests pass.

## Step 4: Finalize

If you successfully fixed the FIXME and all tests pass:
1. Remove the FIXME comment (and its additional context lines).
2. Commit your changes.
3. Either update (if it exists) or create (if it does not exist) a PR \
titled "fixme-fairy: <short description of the fix>".

If you were unable to fix the FIXME and get all tests passing:
1. Revert any changes you made while attempting the fix.
2. Update the FIXME to increment the attempts count by 1 (if there were no \
prior attempts, add `[attempts=1]`, if there were some prior attempts, \
increment the number by 1). The `[attempts=N]` part goes before the `:`, \
like: `# FIXME[attempts=1]: (description)` or \
`# FIXME0[attempts=2]: (description)`.
3. Add a brief note to the optional additional context about why you were \
unable to fix it.
4. Commit this updated FIXME (make sure nothing else is being changed).
5. Either update (if it exists) or create (if it does not exist) a PR \
titled "fixme-fairy: attempted <short description> (failed)".
"""


class FixmeFairyAgentConfig(ClaudeAgentConfig):
    """Config for the fixme-fairy agent type."""


def _prompt_user_for_skill_install(skill_path: Path) -> bool:
    """Prompt the user to install or update the fixme-fairy skill."""
    if skill_path.exists():
        logger.info(
            "\nThe fixme-fairy skill at {} will be updated.\n",
            skill_path,
        )
        return click.confirm("Update the fixme-fairy skill?", default=True)
    else:
        logger.info(
            "\nThe fixme-fairy skill will be installed to {}.\n",
            skill_path,
        )
        return click.confirm("Install the fixme-fairy skill?", default=True)


def _install_skill_locally(mng_ctx: MngContext) -> None:
    """Install the fixme-fairy skill to the local user's ~/.claude/skills/."""
    skill_path = Path.home() / ".claude" / "skills" / _SKILL_NAME / "SKILL.md"

    with log_span("Installing fixme-fairy skill to {}", skill_path):
        # Skip if the skill is already installed with the same content
        if skill_path.exists() and skill_path.read_text() == _FIXME_FAIRY_SKILL_CONTENT:
            logger.debug("Fixme-fairy skill is already up to date at {}", skill_path)
            return

        if mng_ctx.is_interactive and not mng_ctx.is_auto_approve:
            if not _prompt_user_for_skill_install(skill_path):
                logger.info("Skipped fixme-fairy skill installation")
                return

        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_FIXME_FAIRY_SKILL_CONTENT)
        logger.debug("Installed fixme-fairy skill to {}", skill_path)


def _install_skill_remotely(host: OnlineHostInterface) -> None:
    """Install the fixme-fairy skill on a remote host."""
    skill_path = Path(f".claude/skills/{_SKILL_NAME}/SKILL.md")

    with log_span("Installing fixme-fairy skill on remote host"):
        host.execute_command(
            f"mkdir -p ~/.claude/skills/{_SKILL_NAME}",
            timeout_seconds=10.0,
        )
        host.write_text_file(skill_path, _FIXME_FAIRY_SKILL_CONTENT)
        logger.debug("Installed fixme-fairy skill on remote host")


class FixmeFairyAgent(ClaudeAgent):
    """Agent implementation for fixme-fairy with skill provisioning."""

    def provision(
        self,
        host: OnlineHostInterface,
        options: CreateAgentOptions,
        mng_ctx: MngContext,
    ) -> None:
        """Provision the fixme-fairy skill and then run standard Claude provisioning."""
        super().provision(host, options, mng_ctx)

        if host.is_local:
            _install_skill_locally(mng_ctx)
        else:
            _install_skill_remotely(host)


@hookimpl
def register_agent_type() -> tuple[str, type[AgentInterface] | None, type[AgentTypeConfig]]:
    """Register the fixme-fairy agent type."""
    return ("fixme-fairy", FixmeFairyAgent, FixmeFairyAgentConfig)
