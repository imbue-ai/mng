"""Shared staging utilities for Modal deployments.

This module previously contained install_deploy_files() which copied staged
files into the container at runtime. That logic has been replaced by
dockerfile_commands that bake the files into their final locations during the
image build (see cron_runner.py). This module is kept as a namespace for any
future staging helpers.

IMPORTANT: This file must NOT import anything from imbue.* packages.
It is imported by cron_runner.py which runs standalone on Modal.
"""
