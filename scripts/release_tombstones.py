"""Publish tombstone packages for the old mng-* PyPI names.

Each tombstone package contains only a README pointing users to the new
imbue-mngr-* package, plus a dependency on the new package so that
`pip install --upgrade mng` automatically pulls in imbue-mngr.

This is a one-shot script. Run it once after the first imbue-mngr-* release
to claim the old names and redirect users.

Usage:
    uv run scripts/release_tombstones.py              # build and publish
    uv run scripts/release_tombstones.py --dry-run     # build only, don't publish
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Old PyPI name -> new PyPI name.
#
# Only packages whose name changed are listed here. Packages that kept their
# name (resource-guards, imbue-common, concurrency-group, modal-proxy) don't
# need tombstones.
# ---------------------------------------------------------------------------
TOMBSTONES: Final[dict[str, str]] = {
    "mng": "imbue-mngr",
    "mng-claude": "imbue-mngr-claude",
    "mng-kanpan": "imbue-mngr-kanpan",
    "mng-modal": "imbue-mngr-modal",
    "mng-opencode": "imbue-mngr-opencode",
    "mng-pair": "imbue-mngr-pair",
    "mng-tutor": "imbue-mngr-tutor",
}

# ---------------------------------------------------------------------------
# TODO: Fill in the correct versions before running this script.
#
# Each tombstone version must be higher than the last published version of
# that old package on PyPI (so that `pip install --upgrade` picks it up).
# The dependency version should be the first imbue-mngr-* release version.
#
# Set each value to "<tombstone_version>,<new_package_version>".
# Example: "0.1.9,0.2.0" means publish the tombstone at 0.1.9, depending
# on imbue-mngr==0.2.0.
# ---------------------------------------------------------------------------
VERSIONS: Final[dict[str, tuple[str, str]]] = {
    "mng": ("TODO", "TODO"),
    "mng-claude": ("TODO", "TODO"),
    "mng-kanpan": ("TODO", "TODO"),
    "mng-modal": ("TODO", "TODO"),
    "mng-opencode": ("TODO", "TODO"),
    "mng-pair": ("TODO", "TODO"),
    "mng-tutor": ("TODO", "TODO"),
}


def _check_versions() -> None:
    """Abort if any version is still a TODO placeholder."""
    missing = [name for name, (tv, dv) in VERSIONS.items() if tv == "TODO" or dv == "TODO"]
    if missing:
        print("ERROR: The following packages still have TODO versions:", file=sys.stderr)
        for name in missing:
            tv, dv = VERSIONS[name]
            print(f"  {name}: tombstone_version={tv}, new_package_version={dv}", file=sys.stderr)
        print(file=sys.stderr)
        print("Fill in VERSIONS in this script before running it.", file=sys.stderr)
        sys.exit(1)


def _make_readme(old_name: str, new_name: str) -> str:
    return textwrap.dedent(f"""\
        # {old_name}

        This package has been renamed to [{new_name}](https://pypi.org/project/{new_name}/).

        Install the new package:

        ```
        pip install {new_name}
        ```
    """)


def _make_pyproject(old_name: str, new_name: str, tombstone_version: str, new_version: str) -> str:
    return textwrap.dedent(f"""\
        [build-system]
        requires = ["hatchling"]
        build-backend = "hatchling.build"

        [project]
        name = "{old_name}"
        version = "{tombstone_version}"
        description = "Renamed to {new_name}. Install {new_name} instead."
        readme = "README.md"
        requires-python = ">=3.11"
        license = "MIT"
        dependencies = ["{new_name}=={new_version}"]
    """)


def _build_tombstone(old_name: str, new_name: str, dist_dir: Path) -> None:
    """Create a temporary package tree and build it into dist_dir."""
    tombstone_version, new_version = VERSIONS[old_name]
    with tempfile.TemporaryDirectory() as tmp:
        pkg_dir = Path(tmp)
        (pkg_dir / "README.md").write_text(_make_readme(old_name, new_name))
        (pkg_dir / "pyproject.toml").write_text(_make_pyproject(old_name, new_name, tombstone_version, new_version))
        subprocess.run(
            ["pyproject-build", str(pkg_dir), "-o", str(dist_dir)],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish tombstone packages for old mng-* PyPI names.")
    parser.add_argument("--dry-run", action="store_true", help="Build only, don't publish to PyPI")
    args = parser.parse_args()

    _check_versions()

    dist_dir = Path(tempfile.mkdtemp(prefix="tombstones-dist-"))
    print(f"Building tombstone packages into {dist_dir}\n")

    for old_name, new_name in sorted(TOMBSTONES.items()):
        print(f"  Building {old_name} -> {new_name}")
        _build_tombstone(old_name, new_name, dist_dir)

    print(f"\nBuilt {len(TOMBSTONES)} tombstone packages.")

    if args.dry_run:
        print(f"\n(dry run -- packages are in {dist_dir})")
        return

    print("\nPublishing to PyPI...")
    subprocess.run(
        ["twine", "upload", str(dist_dir / "*")],
        check=True,
    )
    print("Done. Tombstone packages published.")
    shutil.rmtree(dist_dir)


if __name__ == "__main__":
    main()
