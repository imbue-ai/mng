import tomllib
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).parent.parent

PUBLISHABLE_PACKAGE_PYPROJECT_PATHS: Final[list[Path]] = [
    REPO_ROOT / "libs" / "mng" / "pyproject.toml",
    REPO_ROOT / "libs" / "imbue_common" / "pyproject.toml",
    REPO_ROOT / "libs" / "concurrency_group" / "pyproject.toml",
    REPO_ROOT / "libs" / "mng_pair" / "pyproject.toml",
    REPO_ROOT / "libs" / "mng_opencode" / "pyproject.toml",
]


def get_package_versions() -> dict[str, str]:
    """Read the version from each publishable package. Returns {name: version}."""
    versions: dict[str, str] = {}
    for path in PUBLISHABLE_PACKAGE_PYPROJECT_PATHS:
        data = tomllib.loads(path.read_text())
        versions[data["project"]["name"]] = data["project"]["version"]
    return versions


def check_versions_in_sync() -> str:
    """Verify all packages have the same version. Returns the version, or raises ValueError."""
    versions = get_package_versions()
    unique = set(versions.values())
    if len(unique) != 1:
        raise ValueError(f"Version mismatch across packages: {versions}")
    return unique.pop()
