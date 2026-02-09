"""Tests for the type-safe model_copy update helpers."""

import pytest
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.model_update import NestedFieldUpdateError
from imbue.imbue_common.model_update import to_update
from imbue.imbue_common.model_update import to_update_dict
from imbue.imbue_common.mutable_model import MutableModel


class _SampleFrozenModel(FrozenModel):
    """Test model with a variety of field types."""

    name: str = Field(description="A string field")
    count: int = Field(description="An integer field")
    label: str | None = Field(default=None, description="An optional string field")
    tags: tuple[str, ...] = Field(default=(), description="A tuple field")


class _SampleMutableModel(MutableModel):
    """Test model for MutableModel.field_ref()."""

    value: int = Field(description="An integer field")
    label: str | None = Field(default=None, description="An optional string field")


# -- Runtime behavior tests --


def test_fields_proxy_returns_field_name_as_string() -> None:
    """Accessing a field on the proxy produces a string matching the field name."""
    model = _SampleFrozenModel(name="test", count=1)
    proxy_field = model.field_ref().name

    assert str(proxy_field) == "name"


def test_to_update_returns_field_name_and_value_pair() -> None:
    """to_update extracts the field name string and pairs it with the value."""
    model = _SampleFrozenModel(name="test", count=1)

    result = to_update(model.field_ref().name, "new_name")

    assert result == ("name", "new_name")


def test_to_update_dict_produces_dict_from_pairs() -> None:
    """to_update_dict converts multiple pairs into a single dict."""
    model = _SampleFrozenModel(name="test", count=1)

    result = to_update_dict(
        to_update(model.field_ref().name, "updated"),
        to_update(model.field_ref().count, 42),
    )

    assert result == {"name": "updated", "count": 42}


def test_model_copy_with_to_update_dict_produces_correct_copy() -> None:
    """Full round-trip: field_ref() + to_update + to_update_dict + model_copy."""
    original = _SampleFrozenModel(name="original", count=1, label="old", tags=("a",))

    updated = original.model_copy(
        update=to_update_dict(
            to_update(original.field_ref().name, "updated"),
            to_update(original.field_ref().count, 99),
            to_update(original.field_ref().label, None),
        )
    )

    assert updated.name == "updated"
    assert updated.count == 99
    assert updated.label is None
    assert updated.tags == ("a",)


def test_model_copy_with_single_field_update() -> None:
    """Updating a single field leaves all others unchanged."""
    original = _SampleFrozenModel(name="test", count=5, label="keep", tags=("x", "y"))

    updated = original.model_copy(
        update=to_update_dict(
            to_update(original.field_ref().count, 10),
        )
    )

    assert updated.name == "test"
    assert updated.count == 10
    assert updated.label == "keep"
    assert updated.tags == ("x", "y")


def test_fields_works_on_mutable_model() -> None:
    """field_ref() and to_update work identically on MutableModel subclasses."""
    original = _SampleMutableModel(value=1, label="old")

    updated = original.model_copy(
        update=to_update_dict(
            to_update(original.field_ref().value, 42),
            to_update(original.field_ref().label, "new"),
        )
    )

    assert updated.value == 42
    assert updated.label == "new"


def test_to_update_dict_with_no_args_returns_empty_dict() -> None:
    """to_update_dict with no arguments returns an empty dict."""
    result = to_update_dict()

    assert result == {}


def test_to_update_dict_raises_on_nested_field_path() -> None:
    """to_update_dict rejects dotted paths that pydantic model_copy silently mishandles."""
    with pytest.raises(NestedFieldUpdateError, match="nested.field"):
        to_update_dict(("nested.field", "value"))
