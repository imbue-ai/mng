"""Mind-specific provisioning functions for uploading default content.

Provides provisioning for mind defaults (GLOBAL.md, role prompts, skills)
by uploading the entire defaults/ directory tree to the host. Only files
that do not already exist on the host are written, preserving any
customizations the user has made.
"""

from __future__ import annotations

import importlib.resources
import shlex
from importlib.abc import Traversable
from pathlib import Path

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng_llm.data_types import ProvisioningSettings
from imbue.mng_llm.provisioning import execute_with_timing
from imbue.mng_mind import defaults as defaults_package


def _write_default_if_missing(
    host: OnlineHostInterface,
    target_path: Path,
    content: str,
    settings: ProvisioningSettings,
) -> None:
    """Write a default file to the host if the target doesn't already exist."""
    check = execute_with_timing(
        host,
        f"test -f {shlex.quote(str(target_path))}",
        hard_timeout=settings.fs_hard_timeout_seconds,
        warn_threshold=settings.fs_warn_threshold_seconds,
        label="file check",
    )
    if check.success:
        logger.debug("Default file already exists, skipping: {}", target_path)
        return

    execute_with_timing(
        host,
        f"mkdir -p {shlex.quote(str(target_path.parent))}",
        hard_timeout=settings.fs_hard_timeout_seconds,
        warn_threshold=settings.fs_warn_threshold_seconds,
        label="mkdir",
    )

    with log_span("Writing default content: {}", target_path):
        host.write_text_file(target_path, content)


def _iter_defaults(base: Traversable, prefix: str = "") -> list[tuple[str, str]]:
    """Collect all default files from the traversable directory tree.

    Returns a sorted list of (relative_path, content) pairs for all files
    in the defaults tree. Skips Python infrastructure files (__init__.py,
    __pycache__).
    """
    results: list[tuple[str, str]] = []
    for item in base.iterdir():
        if item.name.startswith("__"):
            continue
        relative = f"{prefix}{item.name}" if not prefix else f"{prefix}/{item.name}"
        if item.is_file():
            results.append((relative, item.read_text()))
        elif item.is_dir():
            results.extend(_iter_defaults(item, relative))
    results.sort(key=lambda pair: pair[0])
    return results


def provision_default_content(
    host: OnlineHostInterface,
    work_dir: Path,
    settings: ProvisioningSettings,
) -> None:
    """Write default content files to the work directory if they don't already exist.

    Walks the entire defaults/ directory tree and uploads all files that
    are missing on the host. This populates sensible defaults for:
    - GLOBAL.md (shared project instructions for all agents)
    - talking/PROMPT.md (talking agent prompt, used as llm system prompt)
    - thinking/PROMPT.md (primary/inner monologue agent prompt)
    - thinking/skills/<name>/SKILL.md (skills for the thinking agent)
    - working/PROMPT.md (working agent prompt)
    - verifying/PROMPT.md (verifying agent prompt)

    Only writes files that are missing -- existing files are never overwritten.
    This allows fresh deployments to work out of the box while preserving
    any customizations the user has already made.
    """
    defaults_root = importlib.resources.files(defaults_package)
    for relative_path, content in _iter_defaults(defaults_root):
        target_path = work_dir / relative_path
        _write_default_if_missing(host, target_path, content, settings)
