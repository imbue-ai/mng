import re
import tomllib

from scripts.utils import PACKAGES
from scripts.utils import get_package_versions
from scripts.utils import normalize_pypi_name
from scripts.utils import parse_dep_name
from scripts.utils import validate_package_graph


def test_package_graph_matches_pyproject_files() -> None:
    """The hard-coded package graph must match the actual pyproject.toml dependency declarations."""
    validate_package_graph()


def test_internal_deps_are_pinned() -> None:
    """All internal dependency references in pyproject.toml must use == pins."""
    internal_names = {pkg.pypi_name for pkg in PACKAGES}

    for pkg in PACKAGES:
        data = tomllib.loads(pkg.pyproject_path.read_text())
        raw_deps: list[str] = data["project"].get("dependencies", [])
        for dep_str in raw_deps:
            dep_name = normalize_pypi_name(parse_dep_name(dep_str))
            if dep_name in internal_names:
                assert re.search(r"==\d", dep_str), (
                    f"{pkg.pypi_name} depends on internal package {dep_name} without an == pin: {dep_str!r}"
                )


def test_internal_dep_pins_match_current_versions() -> None:
    """Pinned versions for internal deps must match the depended-on package's actual version."""
    internal_names = {pkg.pypi_name for pkg in PACKAGES}
    versions = get_package_versions()

    for pkg in PACKAGES:
        data = tomllib.loads(pkg.pyproject_path.read_text())
        raw_deps: list[str] = data["project"].get("dependencies", [])
        for dep_str in raw_deps:
            dep_name = normalize_pypi_name(parse_dep_name(dep_str))
            if dep_name in internal_names:
                # Extract the pinned version
                match = re.search(r"==(.+)$", dep_str)
                assert match is not None, f"{pkg.pypi_name}: internal dep {dep_name} is not pinned: {dep_str!r}"
                pinned_version = match.group(1)
                expected_version = versions[dep_name]
                assert pinned_version == expected_version, (
                    f"{pkg.pypi_name}: pin for {dep_name} is {pinned_version} "
                    f"but {dep_name} is at version {expected_version}"
                )
