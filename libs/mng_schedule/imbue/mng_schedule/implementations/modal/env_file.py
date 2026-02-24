"""Minimal env file parser for use in Modal deployments.

This module must NOT import from imbue.* packages -- it is used by
cron_runner.py which runs standalone on Modal via `modal deploy`.
"""

import os
from pathlib import Path


def load_env_file(env_file_path: Path) -> None:
    """Load environment variables from a .env file into os.environ.

    Lines starting with '#' are treated as comments. Empty lines are skipped.
    Lines without '=' are skipped. The 'export ' prefix is stripped if present
    (to support shell-compatible env files). Values are not shell-unquoted
    (surrounding quotes are kept as literal characters). This is a minimal
    parser; for full dotenv compatibility, use python-dotenv.
    """
    if not env_file_path.exists():
        return
    for line in env_file_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip optional 'export ' prefix for shell-compatible env files
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key.strip()] = value.strip()
