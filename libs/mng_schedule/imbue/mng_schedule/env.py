"""Shared environment variable utilities for the mng_schedule plugin."""

import os
from collections.abc import Sequence
from pathlib import Path

from loguru import logger


def collect_env_lines(
    pass_env: Sequence[str] = (),
    env_files: Sequence[Path] = (),
) -> list[str]:
    """Collect environment variable lines from multiple sources.

    Sources are merged in order of increasing precedence:
    1. User-specified --env-file entries (in order)
    2. User-specified --pass-env variables from the current process environment

    Returns a list of lines in KEY=VALUE format (may also include comments
    and blank lines from env files).
    """
    env_lines: list[str] = []

    for env_file_path in env_files:
        env_lines.extend(env_file_path.read_text().splitlines())
        logger.info("Including env file {}", env_file_path)

    for var_name in pass_env:
        value = os.environ.get(var_name)
        if value is not None:
            env_lines.append(f"{var_name}={value}")
            logger.debug("Passing through env var {}", var_name)
        else:
            logger.warning("Environment variable '{}' not set in current environment, skipping", var_name)

    return env_lines
