#!/usr/bin/env python3
"""Minimal reproduction script for Modal Sandbox.list() bug.

This script demonstrates that Sandbox.list() with app_id and tags filters
fails to return results for sandboxes in non-default environments, even when
the sandbox exists and has the expected tags.

The bug appears to be that querying Sandbox.list(app_id=..., tags={...}) for
a non-default environment returns empty results, even though:
- Sandbox.list(app_id=...) without tags DOES return the sandbox
- The sandbox's get_tags() returns the expected tags
- The tags being queried match exactly

Usage:
    # Step 1: Create the sandbox (in one process)
    uv run python scripts/modal_sandbox_list_bug_repro.py create

    # Step 2: Query the sandbox (in another process, to ensure consistency)
    uv run python scripts/modal_sandbox_list_bug_repro.py query <sandbox_id>

    # Or run both steps in one process:
    uv run python scripts/modal_sandbox_list_bug_repro.py full

    # Cleanup:
    uv run python scripts/modal_sandbox_list_bug_repro.py cleanup
"""

import argparse
import json
import subprocess
import sys
import time

import modal
import modal.exception

# Use a distinctive environment name for this reproduction
REPRO_ENVIRONMENT = "modal-list-bug-repro"
REPRO_APP_NAME = "sandbox-list-bug-repro"
REPRO_TAG_KEY = "repro_tag_key"
REPRO_TAG_VALUE = "repro_tag_value"


def ensure_environment_exists(environment_name: str) -> None:
    """Ensure a Modal environment exists, creating it if necessary."""
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            environments = json.loads(result.stdout)
            for env in environments:
                if env.get("name") == environment_name:
                    print(f"Environment '{environment_name}' already exists")
                    return
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        print(f"Warning: Could not list environments: {e}")

    print(f"Creating environment '{environment_name}'...")
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "create", environment_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"Created environment '{environment_name}'")
        else:
            print(f"Environment create output: {result.stderr}")
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        print(f"Warning: Could not create environment via CLI: {e}")


def create_sandbox() -> str:
    """Create a sandbox in the non-default environment with a tag.

    Returns the sandbox ID.
    """
    print(f"\n=== Creating sandbox in environment '{REPRO_ENVIRONMENT}' ===\n")

    # Ensure the environment exists
    ensure_environment_exists(REPRO_ENVIRONMENT)

    # Create a persistent app in the non-default environment
    print(f"Looking up/creating app '{REPRO_APP_NAME}' in environment '{REPRO_ENVIRONMENT}'...")
    app = modal.App.lookup(REPRO_APP_NAME, create_if_missing=True, environment_name=REPRO_ENVIRONMENT)
    print(f"App ID: {app.app_id}")

    # Define the tags we'll use
    tags = {REPRO_TAG_KEY: REPRO_TAG_VALUE}
    print(f"Tags to set: {tags}")

    # Create a simple sandbox with the tag
    print("\nCreating sandbox...")
    image = modal.Image.debian_slim()
    sandbox = modal.Sandbox.create(
        image=image,
        app=app,
        environment_name=REPRO_ENVIRONMENT,
        timeout=300,  # 5 minute timeout
    )
    sandbox.set_tags(tags)

    print(f"Sandbox ID: {sandbox.object_id}")
    print(f"Tags set on sandbox: {sandbox.get_tags()}")

    # Verify the sandbox is findable by app_id alone
    print("\nVerifying sandbox is listed (app_id only)...")
    found_by_app = list(modal.Sandbox.list(app_id=app.app_id))
    print(f"Sandboxes found by app_id only: {len(found_by_app)}")
    for sb in found_by_app:
        print(f"  - {sb.object_id}: tags={sb.get_tags()}")

    return sandbox.object_id


def query_sandbox(sandbox_id: str) -> bool:
    """Query for the sandbox using app_id and tags.

    Returns True if the bug is reproduced (sandbox not found with tags filter),
    False otherwise.
    """
    print(f"\n=== Querying for sandbox '{sandbox_id}' ===\n")

    # Get the app
    print(f"Looking up app '{REPRO_APP_NAME}' in environment '{REPRO_ENVIRONMENT}'...")
    app = modal.App.lookup(REPRO_APP_NAME, environment_name=REPRO_ENVIRONMENT)
    print(f"App ID: {app.app_id}")

    tags = {REPRO_TAG_KEY: REPRO_TAG_VALUE}

    # First, verify the sandbox exists and has the right tags
    print("\n--- Test 1: List sandboxes by app_id only ---")
    found_by_app = list(modal.Sandbox.list(app_id=app.app_id))
    print(f"Found {len(found_by_app)} sandbox(es) by app_id only")

    target_sandbox = None
    for sb in found_by_app:
        actual_tags = sb.get_tags()
        print(f"  - {sb.object_id}: tags={actual_tags}")
        if sb.object_id == sandbox_id:
            target_sandbox = sb

    if target_sandbox is None:
        print(f"\nERROR: Sandbox {sandbox_id} not found at all!")
        return False

    print(f"\nTarget sandbox found: {target_sandbox.object_id}")
    print(f"Target sandbox tags: {target_sandbox.get_tags()}")

    # Verify the tags match what we're querying for
    actual_tags = target_sandbox.get_tags()
    print("\n--- Verifying tag match ---")
    print(f"Query tags:  {tags}")
    print(f"Actual tags: {actual_tags}")
    print(f"Tags match:  {tags.items() <= actual_tags.items()}")

    # Now try to find it with the tags filter
    print("\n--- Test 2: List sandboxes by app_id AND tags ---")
    print(f"Query: Sandbox.list(app_id='{app.app_id}', tags={tags})")
    found_with_tags = list(modal.Sandbox.list(app_id=app.app_id, tags=tags))
    print(f"Found {len(found_with_tags)} sandbox(es) with app_id + tags filter")
    for sb in found_with_tags:
        print(f"  - {sb.object_id}: tags={sb.get_tags()}")

    # Also try with tags only (no app_id)
    print("\n--- Test 3: List sandboxes by tags only ---")
    print(f"Query: Sandbox.list(tags={tags})")
    found_tags_only = list(modal.Sandbox.list(tags=tags))
    print(f"Found {len(found_tags_only)} sandbox(es) with tags only")
    for sb in found_tags_only:
        print(f"  - {sb.object_id}: tags={sb.get_tags()}")

    # Report the bug
    print("\n" + "=" * 60)
    if len(found_with_tags) == 0:
        print("BUG REPRODUCED!")
        print("")
        print("Summary:")
        print(f"  - Sandbox {sandbox_id} EXISTS (found by app_id only)")
        print(f"  - Sandbox has tags: {actual_tags}")
        print(f"  - Query tags match: {tags}")
        print("  - But Sandbox.list(app_id=..., tags=...) returns EMPTY!")
        print("")
        print("This appears to be a Modal bug where Sandbox.list() with both")
        print("app_id and tags filters fails for non-default environments.")
        return True
    else:
        print("Bug NOT reproduced - sandbox was found with tags filter")
        return False


def full_test() -> bool:
    """Run the full test: create sandbox and query it."""
    sandbox_id = create_sandbox()

    # Add a small delay to allow for eventual consistency
    print("\nWaiting 5 seconds for eventual consistency...")
    time.sleep(5)

    return query_sandbox(sandbox_id)


def cleanup() -> None:
    """Clean up the reproduction resources."""
    print(f"\n=== Cleaning up resources in environment '{REPRO_ENVIRONMENT}' ===\n")

    try:
        app = modal.App.lookup(REPRO_APP_NAME, environment_name=REPRO_ENVIRONMENT)
        print(f"Found app '{REPRO_APP_NAME}' (ID: {app.app_id})")

        # Terminate any sandboxes
        sandboxes = list(modal.Sandbox.list(app_id=app.app_id))
        print(f"Found {len(sandboxes)} sandbox(es) to terminate")
        for sb in sandboxes:
            print(f"  Terminating {sb.object_id}...")
            try:
                sb.terminate()
            except Exception as e:
                print(f"    Warning: {e}")

        print("\nNote: The app and environment are left in place.")
        print("To fully clean up, use the Modal dashboard or CLI:")
        print(f"  modal app delete {REPRO_APP_NAME} --env {REPRO_ENVIRONMENT}")
        print(f"  modal environment delete {REPRO_ENVIRONMENT}")

    except modal.exception.NotFoundError:
        print(f"App '{REPRO_APP_NAME}' not found in environment '{REPRO_ENVIRONMENT}'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reproduce Modal Sandbox.list() bug with non-default environments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("create", help="Create a sandbox and print its ID")
    query_parser = subparsers.add_parser("query", help="Query for a sandbox by ID")
    query_parser.add_argument("sandbox_id", help="The sandbox ID to query for")
    subparsers.add_parser("full", help="Run full test (create + query)")
    subparsers.add_parser("cleanup", help="Clean up reproduction resources")

    args = parser.parse_args()

    if args.command == "create":
        sandbox_id = create_sandbox()
        print(f"\nSandbox created: {sandbox_id}")
        print("\nTo query (in a separate process):")
        print(f"  uv run python scripts/modal_sandbox_list_bug_repro.py query {sandbox_id}")
        return 0

    elif args.command == "query":
        bug_reproduced = query_sandbox(args.sandbox_id)
        return 0 if bug_reproduced else 1

    elif args.command == "full":
        bug_reproduced = full_test()
        return 0 if bug_reproduced else 1

    elif args.command == "cleanup":
        cleanup()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
