"""Shared utilities for provider get_files_for_deploy implementations."""

from pathlib import Path

from imbue.mng.config.data_types import MngContext


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
