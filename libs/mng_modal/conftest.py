"""Project-level conftest for mng_modal.

Provides test infrastructure by inheriting from mng's conftest and adding
modal-specific resource cleanup.
"""

import json
import subprocess
from typing import Generator

import pytest

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.imbue_common.conftest_hooks import register_marker
from imbue.mng.utils.logging import suppress_warnings
from imbue.mng.utils.testing import worker_modal_app_names
from imbue.mng.utils.testing import worker_modal_environment_names
from imbue.mng.utils.testing import worker_modal_volume_names
from imbue.mng_modal.backend import ModalProviderBackend
from imbue.mng_modal.register_guards import register_modal_guard
from imbue.resource_guards.resource_guards import register_resource_guard

suppress_warnings()

register_marker("tmux: marks tests that create real tmux sessions or mng agents")
register_marker("rsync: marks tests that invoke rsync for file transfer")
register_marker("unison: marks tests that start a real unison file-sync process")
register_marker("modal: marks tests that connect to the Modal cloud service")
register_resource_guard("tmux")
register_resource_guard("rsync")
register_resource_guard("unison")
register_resource_guard("modal")
register_modal_guard()

register_conftest_hooks(globals())

# Inherit all fixtures from mng's conftest (same pattern as mng_claude)
pytest_plugins = ["imbue.mng.conftest"]


@pytest.fixture(autouse=True)
def _reset_modal_app_registry() -> Generator[None, None, None]:
    """Reset the Modal app registry after each test for isolation."""
    yield
    ModalProviderBackend.reset_app_registry()


# =============================================================================
# Session Cleanup - Detect and clean up leaked Modal test resources
# =============================================================================


def _get_leaked_modal_apps() -> list[tuple[str, str]]:
    if not worker_modal_app_names:
        return []
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "app", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        apps = json.loads(result.stdout)
        return [
            (app.get("App ID", ""), app.get("Description", ""))
            for app in apps
            if app.get("Description", "") in worker_modal_app_names and app.get("State", "") != "stopped"
        ]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _stop_modal_apps(apps: list[tuple[str, str]]) -> None:
    for app_id, _ in apps:
        try:
            subprocess.run(
                ["uv", "run", "modal", "app", "stop", app_id],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


def _get_leaked_modal_volumes() -> list[str]:
    if not worker_modal_volume_names:
        return []
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "volume", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        volumes = json.loads(result.stdout)
        return [v.get("Name", "") for v in volumes if v.get("Name", "") in worker_modal_volume_names]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _delete_modal_volumes(volume_names: list[str]) -> None:
    for name in volume_names:
        try:
            subprocess.run(
                ["uv", "run", "modal", "volume", "delete", name, "--yes"],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


def _get_leaked_modal_environments() -> list[str]:
    if not worker_modal_environment_names:
        return []
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        envs = json.loads(result.stdout)
        return [e.get("name", "") for e in envs if e.get("name", "") in worker_modal_environment_names]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []


def _delete_modal_environments(environment_names: list[str]) -> None:
    for name in environment_names:
        try:
            subprocess.run(
                ["uv", "run", "modal", "environment", "delete", name, "--yes"],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass


@pytest.fixture(scope="session", autouse=True)
def modal_session_cleanup() -> Generator[None, None, None]:
    """Detect and clean up leaked Modal resources at the end of the test session."""
    yield

    errors: list[str] = []

    leaked_apps = _get_leaked_modal_apps()
    if leaked_apps:
        app_info = [f"  {app_id} ({app_name})" for app_id, app_name in leaked_apps]
        errors.append(
            "Leftover Modal apps found!\n"
            "Tests should destroy their Modal hosts before completing.\n" + "\n".join(app_info)
        )

    leaked_volumes = _get_leaked_modal_volumes()
    if leaked_volumes:
        volume_info = [f"  {name}" for name in leaked_volumes]
        errors.append(
            "Leftover Modal volumes found!\n"
            "Tests should delete their Modal volumes before completing.\n" + "\n".join(volume_info)
        )

    leaked_envs = _get_leaked_modal_environments()
    if leaked_envs:
        env_info = [f"  {name}" for name in leaked_envs]
        errors.append(
            "Leftover Modal environments found!\n"
            "Tests should delete their Modal environments before completing.\n" + "\n".join(env_info)
        )

    _stop_modal_apps(leaked_apps)
    _delete_modal_volumes(leaked_volumes)
    _delete_modal_environments(leaked_envs)

    if errors:
        raise AssertionError(
            "=" * 70
            + "\n"
            + "MODAL SESSION CLEANUP FOUND LEAKED RESOURCES!\n"
            + "=" * 70
            + "\n\n"
            + "\n\n".join(errors)
            + "\n\n"
            + "These resources have been cleaned up, but tests should not leak!\n"
        )
