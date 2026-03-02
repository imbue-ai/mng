from scripts.utils import validate_package_graph
from scripts.utils import verify_pin_consistency


def test_package_graph_matches_pyproject_files() -> None:
    """The hard-coded package graph must match the actual pyproject.toml dependency declarations."""
    validate_package_graph()


def test_internal_dep_pins_are_consistent() -> None:
    """All internal deps must use == pins that match the depended-on package's actual version."""
    errors = verify_pin_consistency()
    assert not errors, "\n".join(errors)
