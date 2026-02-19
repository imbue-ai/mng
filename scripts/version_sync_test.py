import tomllib

from scripts.utils import PUBLISHABLE_PACKAGE_PYPROJECT_PATHS


def test_all_package_versions_match() -> None:
    """All publishable packages must have the same version string."""
    versions: dict[str, str] = {}
    for path in PUBLISHABLE_PACKAGE_PYPROJECT_PATHS:
        data = tomllib.loads(path.read_text())
        name = data["project"]["name"]
        version = data["project"]["version"]
        versions[name] = version

    unique_versions = set(versions.values())
    assert len(unique_versions) == 1, (
        f"Version mismatch across packages: {versions}. All packages must have the same version."
    )
