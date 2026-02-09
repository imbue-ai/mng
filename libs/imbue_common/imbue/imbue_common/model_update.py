from typing import Any
from typing import TypeVar

from imbue.imbue_common.pure import pure

_T = TypeVar("_T")


class NestedFieldUpdateError(ValueError):
    """Raised when to_update_dict receives a dotted (nested) field path.

    Pydantic's model_copy(update=...) only supports top-level field keys. Dotted
    keys like "nested.field" are silently accepted but create a hidden attribute
    instead of updating the nested field. This is a known pydantic limitation:
    https://github.com/pydantic/pydantic/issues/12312

    If nested field updates become necessary, a workaround can be built on top
    of this module.
    """


class FieldProxy:
    """Proxy that records attribute access paths for type-safe model_copy updates.

    Used by FrozenModel.field_ref() and MutableModel.field_ref() to create type-safe
    references to model fields. The type checker sees field_ref() as returning Self,
    so attribute access (e.g. model.field_ref().idle_mode) resolves to the field's
    declared type. to_update() then constrains the value to match that type.

    Usage:
        updated = my_model.model_copy(
            update=to_update_dict(
                to_update(my_model.field_ref().some_field, new_value),
                to_update(my_model.field_ref().other_field, other_value),
            )
        )

    Only single-level field access is supported. Chained access like
    model.field_ref().nested.child produces a dotted path ("nested.child") which
    pydantic's model_copy silently mishandles. to_update_dict() raises
    NestedFieldUpdateError if any key contains a dot.
    """

    __slots__ = ("_path",)

    def __init__(self, path: str = "") -> None:
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> "FieldProxy":
        current_path: str = object.__getattribute__(self, "_path")
        new_path = f"{current_path}.{name}" if current_path else name
        return FieldProxy(new_path)

    def __str__(self) -> str:
        return object.__getattribute__(self, "_path")

    def __repr__(self) -> str:
        path = object.__getattribute__(self, "_path")
        return f"FieldProxy({path!r})"


@pure
def to_update(field: _T, value: _T) -> tuple[str, Any]:
    """Create a type-safe (field_name, value) pair for model_copy updates.

    The type checker infers _T from the field proxy (which appears as the field's
    declared type due to field_ref() returning Self), then checks that value matches.
    At runtime, field is a FieldProxy whose str() gives the field name.
    """
    return (str(field), value)


@pure
def to_update_dict(*updates: tuple[str, Any]) -> dict[str, Any]:
    """Convert (field_name, value) pairs into a dict for model_copy(update=...).

    Raises NestedFieldUpdateError if any field name contains a dot, because
    pydantic's model_copy silently mishandles dotted keys instead of updating
    nested fields. See https://github.com/pydantic/pydantic/issues/12312
    """
    for field_name, _value in updates:
        if "." in field_name:
            raise NestedFieldUpdateError(
                f"Nested field updates are not supported by pydantic model_copy: {field_name!r}. "
                f"See https://github.com/pydantic/pydantic/issues/12312"
            )
    return dict(updates)
