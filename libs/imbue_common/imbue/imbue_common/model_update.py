from typing import Any
from typing import TypeVar

from imbue.imbue_common.pure import pure

_T = TypeVar("_T")


class FieldProxy:
    """Proxy that records attribute access paths for type-safe model_copy updates.

    Used by FrozenModel.fields() and MutableModel.fields() to create type-safe
    references to model fields. The type checker sees fields() as returning Self,
    so attribute access (e.g. model.fields().idle_mode) resolves to the field's
    declared type. to_update() then constrains the value to match that type.

    Usage:
        updated = my_model.model_copy(
            update=to_update_dict(
                to_update(my_model.fields().some_field, new_value),
                to_update(my_model.fields().other_field, other_value),
            )
        )
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
    declared type due to fields() returning Self), then checks that value matches.
    At runtime, field is a FieldProxy whose str() gives the field name.
    """
    return (str(field), value)


@pure
def to_update_dict(*updates: tuple[str, Any]) -> dict[str, Any]:
    """Convert (field_name, value) pairs into a dict for model_copy(update=...)."""
    return dict(updates)
