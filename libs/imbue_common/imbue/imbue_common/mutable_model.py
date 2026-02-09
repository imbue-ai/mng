from typing import Self

from pydantic import BaseModel
from pydantic import ConfigDict

from imbue.imbue_common.model_update import FieldProxy


class MutableModel(BaseModel):
    """Base class for mutable pydantic models that allow attribute mutation after construction."""

    model_config = ConfigDict(
        frozen=False,
        extra="forbid",
        arbitrary_types_allowed=False,
    )

    def field_ref(self) -> Self:
        """Return a proxy for type-safe field references with to_update()."""
        return FieldProxy()  # type: ignore[return-value]
