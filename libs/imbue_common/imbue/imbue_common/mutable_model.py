from pydantic import BaseModel
from pydantic import ConfigDict


class MutableModel(BaseModel):
    """Base class for mutable pydantic models that allow attribute mutation after construction."""

    model_config = ConfigDict(frozen=False)
