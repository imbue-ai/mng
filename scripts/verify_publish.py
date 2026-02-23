"""Pre-publish verification for CI: check versions and pin consistency.

Called from the publish workflow before building packages. Verifies:
1. Displays all package versions
2. If --expected-mng-version is given, checks mng version matches (for tag/dispatch checks)
3. All internal dependency pins are consistent

Usage:
    uv run scripts/verify_publish.py
    uv run scripts/verify_publish.py --expected-mng-version 0.1.5
"""

import argparse
import sys

from utils import get_package_versions
from utils import verify_pin_consistency


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-publish verification.")
    parser.add_argument(
        "--expected-mng-version",
        help="If set, verify the mng package version matches this value",
    )
    args = parser.parse_args()

    # Display all package versions
    versions = get_package_versions()
    print("=== Package versions ===")
    for name, version in versions.items():
        print(f"  {name}: {version}")

    # Optionally verify mng version matches an expected value (tag or dispatch input)
    if args.expected_mng_version is not None:
        mng_version = versions["mng"]
        if mng_version != args.expected_mng_version:
            print(
                f"\nERROR: Expected mng version {args.expected_mng_version} but found {mng_version}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"\nmng version matches expected: {mng_version}")

    # Verify pin consistency
    print("\n=== Pin consistency check ===")
    errors = verify_pin_consistency()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
    print("All internal dependency pins are consistent.")


if __name__ == "__main__":
    main()
