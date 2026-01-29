#!/usr/bin/env python3
"""Create a Modal sandbox for mngr tests and print its ID."""
import os
import sys
from pathlib import Path

import modal

modal.enable_output()

# Default to the directory containing this script's grandparent (scripts/shotgun -> mngr)
MNGR_PATH = os.environ.get("MNGR_PATH", str(Path(__file__).parent.parent.parent))

print(f"Using MNGR_PATH: {MNGR_PATH}", file=sys.stderr)
print("Creating Modal app...", file=sys.stderr)
app = modal.App.lookup("shotgun-mngr", create_if_missing=True)

print("Building image with dependencies...", file=sys.stderr)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git",
        "tmux",
        "rsync",
    )
    # Initialize /app as a git repo so ratchet tests work
    .run_commands(
        "git config --global user.email 'test@example.com'",
        "git config --global user.name 'Test User'",
        "git config --global init.defaultBranch main",
    )
    .pip_install(
        # ===== imbue-common dependencies =====
        "click>=8.0",
        "cowsay-python>=1.0.2",
        "deal>=4.24",
        "httpx>=0.27",
        "inline-snapshot>=0.13",
        "loguru>=0.7",
        "pydantic>=2.0",
        "tenacity>=8.0",
        # ===== mngr dependencies =====
        "cel-python>=0.1.5",
        "click-option-group>=0.5.6",
        "coolname>=2.2.0,<3.0.0",  # Pin to 2.x for compatibility
        "cryptography>=42.0",
        "dockerfile-parse>=2.0.0",
        "modal>=0.67",
        "psutil>=5.9",
        "pyinfra>=3.0",
        "pluggy>=1.5.0",
        "tabulate>=0.9.0",
        "tomlkit>=0.12.0",
        "urwid>=2.2.0",
        # ===== concurrency_group dependencies =====
        "anyio>=4.4",
        # ===== test dependencies =====
        "pytest>=7.0",
        "pytest-asyncio",
        "pytest-mock",
        "pytest-timeout>=2.3.0",
        "pytest-cov>=7.0.0",
        "pytest-xdist>=3.8.0",
        "coverage>=7.0",
        # ===== dev tools for ratchet tests =====
        "ruff>=0.12.0",
        "ty>=0.0.8",
        "uv",  # Required for test_no_type_errors which runs "uv run ty check"
        # ===== Additional deps for type checking apps/ =====
        "fastapi",
        "uvicorn",
        "flask",
    )
    # Set PYTHONPATH and other env vars
    .env({
        "PYTHONPATH": "/app/libs/imbue_common:/app/libs/mngr:/app/libs/mngr_opencode:/app/libs/concurrency_group:/app/libs/flexmux:/app/apps/claude_web_view:/app/apps/sculptor_desktop:/app/apps/sculptor_web",
        "EDITOR": "cat",  # Simple editor for tests that check --edit-message flag validation
        "VISUAL": "cat",
        # Unset HISTFILE so test_unset_vars_applied_during_agent_start passes
        # (the test expects HISTFILE to be unset, but debian bash sets it by default)
        "HISTFILE": "",
    })
    # Mirror the exact source structure so test paths match
    # Using copy=True so we can run git init after adding files
    .add_local_dir(f"{MNGR_PATH}/libs", "/app/libs", ignore=["*.pyc", "__pycache__", ".venv", "venv", "node_modules"], copy=True)
    .add_local_dir(f"{MNGR_PATH}/apps", "/app/apps", ignore=["*.pyc", "__pycache__", ".venv", "venv", "node_modules"], copy=True)
    # Include root conftest.py for test fixtures
    .add_local_file(f"{MNGR_PATH}/conftest.py", "/app/conftest.py", copy=True)
    # Include pyproject.toml for pytest configuration
    .add_local_file(f"{MNGR_PATH}/pyproject.toml", "/app/pyproject.toml", copy=True)
    # Initialize git repo after adding files (required for ratchet tests)
    .run_commands(
        "cd /app && git init && git add -A && git commit -m 'Initial commit for tests'"
    )
    # Install local packages so entry points work (required for opencode plugin)
    # Also install apps so type checker can find all dependencies
    .run_commands(
        "pip install -e /app/libs/imbue_common",
        "pip install -e /app/libs/mngr",
        "pip install -e /app/libs/mngr_opencode",
        "pip install -e /app/libs/concurrency_group",
        "pip install -e /app/libs/flexmux",
        "pip install -e /app/apps/claude_web_view",
        "pip install -e /app/apps/sculptor_desktop || true",  # May not exist
        "pip install -e /app/apps/sculptor_web || true",  # May not exist
    )
    # Run uv sync to create proper venv for type checker tests
    .run_commands(
        "cd /app && uv sync --all-packages"
    )
)

if __name__ == "__main__":
    print("Creating sandbox...", file=sys.stderr)
    try:
        sandbox = modal.Sandbox.create(
            app=app,
            image=image,
            workdir="/app",
            timeout=3600,
        )
        print(f"Sandbox ready: {sandbox.object_id}", file=sys.stderr)
        print(sandbox.object_id)
    except Exception as e:
        print(f"Error creating sandbox: {e}", file=sys.stderr)
        raise
