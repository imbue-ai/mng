#!/usr/bin/env python3
"""Nuke all Modal resources and local mngr state.

Use this when mngr state gets out of sync with Modal -- for example, after
manually editing ~/.mngr/data.json or when <host_id>.json files on the Modal
volume are outdated and `mngr destroy` no longer works.

This script bypasses mngr entirely and uses the Modal CLI directly.

It will:
  1. Stop all Modal apps in the mngr environment
  2. Delete all Modal volumes in the mngr environment
  3. Delete ~/.mngr/data.json (the local host's certified data)

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

DEFAULT_HOST_DIR = Path("~/.mngr")
DEFAULT_PREFIX = "mngr-"


def _read_user_id(host_dir: Path) -> str | None:
    """Read the user_id from the mngr profile directory."""
    config_path = host_dir / "config.toml"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "rb") as f:
            root_config = tomllib.load(f)
        profile_id = root_config.get("profile")
        if not profile_id:
            return None
        user_id_path = host_dir / "profiles" / profile_id / "user_id"
        if user_id_path.exists():
            return user_id_path.read_text().strip()
    except (tomllib.TOMLDecodeError, OSError):
        pass
    return None


def _detect_environment(host_dir: Path, prefix: str) -> str | None:
    """Auto-detect the Modal environment name from the mngr profile."""
    user_id = _read_user_id(host_dir)
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
    except json.JSONDecodeError:
        return []


def _list_apps(environment: str) -> list[dict[str, str]]:
    """List all apps in the given environment."""
    result = _run_modal(["app", "list", "--json"], environment)
    if result.returncode != 0:
        print(f"Warning: Failed to list apps: {result.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


def _stop_app(app_name: str, environment: str) -> bool:
    """Stop a Modal app."""
    result = _run_modal(["app", "stop", app_name], environment)
    return result.returncode == 0


def _delete_volume(volume_name: str, environment: str) -> bool:
    """Delete a Modal volume."""
    result = _run_modal(["volume", "delete", volume_name, "-y"], environment)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nuke all Modal resources and local mngr state. Use when mngr state is out of sync with Modal.",
    )
    parser.add_argument(
        "--environment",
        "-e",
        help="Modal environment name (auto-detected from ~/.mngr profile if not specified)",
    )
    parser.add_argument(
        "--host-dir",
        type=Path,
        default=DEFAULT_HOST_DIR,
        help=f"Path to mngr host directory (default: {DEFAULT_HOST_DIR})",
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
    args = parser.parse_args()

    host_dir = args.host_dir.expanduser()

    # Auto-detect environment
    environment = args.environment or _detect_environment(host_dir, args.prefix)
    if environment is None:
        print(
            "Could not auto-detect Modal environment. Use --environment to specify it explicitly.",
            file=sys.stderr,
        )
        return 1

    print(f"Modal environment: {environment}")
    print()

    # Discover resources
    apps = _list_apps(environment)
    volumes = _list_volumes(environment)
    data_json = host_dir / "data.json"
    has_data_json = data_json.exists()

    # Show what will be nuked
    if apps:
        print(f"Apps to stop ({len(apps)}):")
        for app in apps:
            app_id = app.get("App ID", app.get("app_id", app.get("id", "unknown")))
            description = app.get("Description", app.get("description", app.get("name", "")))
            print(f"  {app_id}  {description}")
    else:
        print("No apps found.")

    if volumes:
        print(f"Volumes to delete ({len(volumes)}):")
        for vol in volumes:
            vol_name = vol.get("Name", vol.get("name", "unknown"))
            print(f"  {vol_name}")
    else:
        print("No volumes found.")

    if has_data_json:
        print(f"Local file to delete: {data_json}")
    else:
        print(f"No local data.json found at {data_json}")

    print()

    if not apps and not volumes and not has_data_json:
        print("Nothing to nuke.")
        return 0

    if args.dry_run:
        print("Dry run -- no changes made.")
        return 0

    # Confirm
    if not args.force:
        response = input("Proceed with nuke? [y/N] ")
        if response.lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    # Stop apps
    for app in apps:
        app_id = app.get("App ID", app.get("app_id", app.get("id", "unknown")))
        print(f"Stopping app {app_id}...", end=" ", flush=True)
        if _stop_app(app_id, environment):
            print("done")
        else:
            print("FAILED (may already be stopped)")

    # Delete volumes
    for vol in volumes:
        vol_name = vol.get("Name", vol.get("name", "unknown"))
        print(f"Deleting volume {vol_name}...", end=" ", flush=True)
        if _delete_volume(vol_name, environment):
            print("done")
        else:
            print("FAILED")

    # Delete data.json
    if has_data_json:
        print(f"Deleting {data_json}...", end=" ", flush=True)
        try:
            data_json.unlink()
            print("done")
        except OSError as e:
            print(f"FAILED: {e}")

    print()
    print("Nuke complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
