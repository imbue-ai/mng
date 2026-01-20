from pydantic import BaseModel
from pydantic import ConfigDict


class FrozenModel(BaseModel):
    """Base class for immutable pydantic models that prevent attribute mutation after construction."""

    model_config = ConfigDict(frozen=True)
