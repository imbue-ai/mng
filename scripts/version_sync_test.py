import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

PACKAGES = [
    REPO_ROOT / "libs" / "mngr" / "pyproject.toml",
    REPO_ROOT / "libs" / "imbue_common" / "pyproject.toml",
    REPO_ROOT / "libs" / "concurrency_group" / "pyproject.toml",
]


def test_all_package_versions_match() -> None:
    """All publishable packages must have the same version string."""
    versions: dict[str, str] = {}
    for path in PACKAGES:
        data = tomllib.loads(path.read_text())
        name = data["project"]["name"]
        version = data["project"]["version"]
        versions[name] = version

    unique_versions = set(versions.values())
    assert len(unique_versions) == 1, (
        f"Version mismatch across packages: {versions}. All packages must have the same version."
    )
