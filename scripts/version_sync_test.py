from scripts.utils import check_versions_in_sync


def test_all_package_versions_match() -> None:
    """All publishable packages must have the same version string."""
    check_versions_in_sync()
