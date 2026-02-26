"""Tests for CLI command aliases."""

import pytest

from imbue.mng.main import cli
from imbue.mng.utils.click_utils import detect_alias_to_canonical

# Build (alias, canonical) pairs from the CLI group for parametrized test
_ALL_ALIAS_PAIRS: list[tuple[str, str]] = sorted(detect_alias_to_canonical(cli).items())


@pytest.mark.parametrize(("alias", "canonical"), _ALL_ALIAS_PAIRS, ids=[a for a, _ in _ALL_ALIAS_PAIRS])
def test_alias_registered_and_points_to_canonical(alias: str, canonical: str) -> None:
    """Every detected alias must be registered and point to the canonical command."""
    assert alias in cli.commands, f"Alias '{alias}' not registered via cli.add_command"
    assert cli.commands[alias] is cli.commands[canonical], f"Alias '{alias}' does not point to '{canonical}'"
