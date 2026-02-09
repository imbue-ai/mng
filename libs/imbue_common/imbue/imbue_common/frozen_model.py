from typing import Self

from pydantic import BaseModel
from pydantic import ConfigDict

from imbue.imbue_common.model_update import FieldProxy


class FrozenModel(BaseModel):
    """Base class for immutable pydantic models that prevent attribute mutation after construction."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=False,
    )

    def fields(self) -> Self:
        """Return a proxy for type-safe field references with to_update()."""
        return FieldProxy()  # type: ignore[return-value]
