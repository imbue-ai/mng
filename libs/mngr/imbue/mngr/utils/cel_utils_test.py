"""Tests for CEL filter utilities."""

from imbue.mngr.utils.cel_utils import apply_cel_filters_to_context
from imbue.mngr.utils.cel_utils import compile_cel_filters


def test_cel_string_contains_method() -> None:
    """CEL string contains() should work on context values."""
    includes, excludes = compile_cel_filters(
        include_filters=('name.contains("prod")',),
        exclude_filters=(),
    )
    matches = apply_cel_filters_to_context(
        context={"name": "my-prod-agent"},
        include_filters=includes,
        exclude_filters=excludes,
        error_context_description="test",
    )
    assert matches is True

    no_match = apply_cel_filters_to_context(
        context={"name": "my-dev-agent"},
        include_filters=includes,
        exclude_filters=excludes,
        error_context_description="test",
    )
    assert no_match is False


def test_cel_string_starts_with_method() -> None:
    """CEL string startsWith() should work on context values."""
    includes, excludes = compile_cel_filters(
        include_filters=('name.startsWith("staging-")',),
        exclude_filters=(),
    )
    matches = apply_cel_filters_to_context(
        context={"name": "staging-app"},
        include_filters=includes,
        exclude_filters=excludes,
        error_context_description="test",
    )
    assert matches is True

    no_match = apply_cel_filters_to_context(
        context={"name": "prod-app"},
        include_filters=includes,
        exclude_filters=excludes,
        error_context_description="test",
    )
    assert no_match is False


def test_cel_string_ends_with_method() -> None:
    """CEL string endsWith() should work on context values."""
    includes, excludes = compile_cel_filters(
        include_filters=('name.endsWith("-dev")',),
        exclude_filters=(),
    )
    matches = apply_cel_filters_to_context(
        context={"name": "myapp-dev"},
        include_filters=includes,
        exclude_filters=excludes,
        error_context_description="test",
    )
    assert matches is True
