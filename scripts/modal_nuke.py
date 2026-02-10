#!/usr/bin/env python3
"""Nuke all Modal resources for this mngr installation.

Use this when mngr state gets out of sync with Modal -- for example, when
<host_id>.json files on the Modal volume are outdated and `mngr destroy`
no longer works.

This script bypasses mngr entirely and uses the Modal CLI directly.

It will:
  1. Stop all Modal apps in the mngr environment
  2. Delete all Modal volumes in the mngr environment

Usage:
    uv run python scripts/modal_nuke.py
    uv run python scripts/modal_nuke.py --dry-run
    uv run python scripts/modal_nuke.py -e mngr-<user_id>
"""

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_MNGR_DIR = Path("~/.mngr")
DEFAULT_PREFIX = "mngr-"


def _get_app_id(app: dict[str, str]) -> str:
    """Extract app ID from a Modal app dict."""
    return app.get("App ID", app.get("app_id", app.get("id", "unknown")))


def _get_volume_name(vol: dict[str, str]) -> str:
    """Extract volume name from a Modal volume dict."""
    return vol.get("Name", vol.get("name", "unknown"))


def _read_user_id(mngr_dir: Path) -> str | None:
    """Read the user_id from the mngr profile directory."""
    config_path = mngr_dir / "config.toml"
    if not config_path.exists():
        return None
    try:
        with config_path.open("rb") as f:
            root_config = tomllib.load(f)
        profile_id = root_config.get("profile")
        if not profile_id:
            return None
        user_id_path = mngr_dir / "profiles" / profile_id / "user_id"
        if user_id_path.exists():
            return user_id_path.read_text().strip()
    except (tomllib.TOMLDecodeError, OSError) as exc:
        print(f"Warning: Failed to read config: {exc}", file=sys.stderr)
    return None


def _detect_environment(mngr_dir: Path, prefix: str) -> str | None:
    """Auto-detect the Modal environment name from the mngr profile."""
    user_id = _read_user_id(mngr_dir=mngr_dir)
    if user_id:
        return f"{prefix}{user_id}"
    return None


def _run_modal(args: list[str], environment: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a modal CLI command."""
    cmd = ["modal"] + args
    if environment:
        cmd.extend(["-e", environment])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _list_volumes(environment: str) -> list[dict[str, str]]:
    """List all volumes in the given environment."""
    result = _run_modal(["volume", "list", "--json"], environment)
    if result.returncode != 0:
        print(f"Warning: Failed to list volumes: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"Warning: Failed to parse volume list JSON: {exc}", file=sys.stderr)
        return []


def _list_apps(environment: str) -> list[dict[str, str]]:
    """List all apps in the given environment."""
    result = _run_modal(["app", "list", "--json"], environment)
    if result.returncode != 0:
        print(f"Warning: Failed to list apps: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"Warning: Failed to parse app list JSON: {exc}", file=sys.stderr)
        return []


def _stop_app(app_id: str, environment: str) -> bool:
    """Stop a Modal app."""
    result = _run_modal(["app", "stop", app_id], environment)
    return result.returncode == 0


def _delete_volume(volume_name: str, environment: str) -> bool:
    """Delete a Modal volume."""
    result = _run_modal(["volume", "delete", volume_name, "-y"], environment)
    return result.returncode == 0


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Nuke all Modal resources for this mngr installation. "
        "Use when mngr state is out of sync with Modal.",
    )
    parser.add_argument(
        "--environment",
        "-e",
        help="Modal environment name (auto-detected from ~/.mngr profile if not specified)",
    )
    parser.add_argument(
        "--mngr-dir",
        type=Path,
        default=DEFAULT_MNGR_DIR,
        help=f"Path to mngr directory (default: {DEFAULT_MNGR_DIR})",
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Mngr prefix (default: {DEFAULT_PREFIX})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    return parser.parse_args()


def _resolve_environment(args: argparse.Namespace) -> str | None:
    """Resolve the Modal environment from args or auto-detection."""
    mngr_dir = args.mngr_dir.expanduser()
    return args.environment or _detect_environment(mngr_dir, args.prefix)


def _display_resources(apps: list[dict[str, str]], volumes: list[dict[str, str]]) -> bool:
    """Print what will be nuked. Returns True if there is anything to nuke."""
    if apps:
        print(f"Apps to stop ({len(apps)}):")
        for app in apps:
            description = app.get("Description", app.get("description", app.get("name", "")))
            print(f"  {_get_app_id(app)}  {description}")
    else:
        print("No apps found.")

    if volumes:
        print(f"Volumes to delete ({len(volumes)}):")
        for vol in volumes:
            print(f"  {_get_volume_name(vol)}")
    else:
        print("No volumes found.")

    print()
    return bool(apps or volumes)


def _confirm_nuke(is_force: bool) -> bool:
    """Prompt user for confirmation. Returns True if confirmed."""
    if is_force:
        return True
    response = input("Proceed with nuke? [y/N] ")
    return response.lower() in ("y", "yes")


def _execute_nuke(apps: list[dict[str, str]], volumes: list[dict[str, str]], environment: str) -> None:
    """Stop apps and delete volumes."""
    for app in apps:
        aid = _get_app_id(app)
        print(f"Stopping app {aid}...", end=" ", flush=True)
        if _stop_app(aid, environment):
            print("done")
        else:
            print("FAILED (may already be stopped)")

    for vol in volumes:
        vname = _get_volume_name(vol)
        print(f"Deleting volume {vname}...", end=" ", flush=True)
        if _delete_volume(vname, environment):
            print("done")
        else:
            print("FAILED")


def main() -> int:
    args = _parse_args()

    environment = _resolve_environment(args)
    if environment is None:
        print(
            "Could not auto-detect Modal environment. Use --environment to specify it explicitly.",
            file=sys.stderr,
        )
        return 1

    print(f"Modal environment: {environment}")
    print()

    apps = _list_apps(environment)
    volumes = _list_volumes(environment)

    has_resources = _display_resources(apps, volumes)
    if not has_resources:
        print("Nothing to nuke.")
        return 0

    if args.dry_run:
        print("Dry run -- no changes made.")
        return 0

    if not _confirm_nuke(args.force):
        print("Aborted.")
        return 1

    _execute_nuke(apps, volumes, environment)

    print()
    print("Nuke complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
