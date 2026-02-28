"""Shared utilities for provider get_files_for_deploy implementations."""

from pathlib import Path

from loguru import logger

from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError


def collect_provider_profile_files(
    mng_ctx: MngContext,
    provider_name: str,
    excluded_file_names: frozenset[str],
) -> dict[Path, Path | str]:
    """Collect non-secret files from a provider's profile directory for deployment.

    Scans the provider's subdirectory under the profile (e.g.
    ~/.mng/profiles/<id>/providers/<provider_name>/) and returns all files
    except those whose names appear in excluded_file_names (typically SSH
    keypairs and known_hosts).

    Returns dict mapping destination paths (starting with "~/") to local
    source paths.
    """
    files: dict[Path, Path | str] = {}
    provider_dir = mng_ctx.profile_dir / "providers" / provider_name
    if not provider_dir.is_dir():
        return files

    user_home = Path.home()
    for file_path in provider_dir.rglob("*"):
        if file_path.is_file() and file_path.name not in excluded_file_names:
            relative = file_path.relative_to(user_home)
            files[Path(f"~/{relative}")] = file_path
    return files


def collect_deploy_files(
    mng_ctx: MngContext,
    repo_root: Path,
    include_user_settings: bool = True,
    include_project_settings: bool = True,
) -> dict[Path, Path | str]:
    """Collect all files for deployment by calling the get_files_for_deploy hook.

    Calls the get_files_for_deploy hook on all registered plugins and merges
    the results into a single dict. Used by both mng_schedule (for image building)
    and mng_recursive (for provisioning-time injection).

    Destination paths must either start with "~" (user home files) or be
    relative paths (project files). Absolute paths that do not start with
    "~" are rejected with a ValueError.
    """
    all_results: list[dict[Path, Path | str]] = mng_ctx.pm.hook.get_files_for_deploy(
        mng_ctx=mng_ctx,
        include_user_settings=include_user_settings,
        include_project_settings=include_project_settings,
        repo_root=repo_root,
    )
    merged: dict[Path, Path | str] = {}
    for result in all_results:
        for dest_path, source in result.items():
            dest_str = str(dest_path)
            if dest_str.startswith("/"):
                raise MngError(f"Deploy file destination path must be relative or start with '~', got: {dest_path}")
            if dest_path in merged:
                logger.warning(
                    "Deploy file collision: {} registered by multiple plugins, overwriting previous value",
                    dest_path,
                )
            merged[dest_path] = source
    return merged
