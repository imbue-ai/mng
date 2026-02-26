from abc import ABC
from abc import abstractmethod
from collections.abc import Mapping

from pydantic import Field

from imbue.changelings.primitives import ChangelingName
from imbue.imbue_common.mutable_model import MutableModel


class BackendResolverInterface(MutableModel, ABC):
    """Resolves changeling names to their backend server URLs."""

    @abstractmethod
    def get_backend_url(self, changeling_name: ChangelingName) -> str | None:
        """Return the backend URL for a changeling, or None if unknown/offline."""

    @abstractmethod
    def list_known_changeling_names(self) -> tuple[ChangelingName, ...]:
        """Return all known changeling names."""


class StaticBackendResolver(BackendResolverInterface):
    """Resolves backend URLs from a static mapping provided at construction time."""

    url_by_changeling_name: Mapping[str, str] = Field(
        frozen=True,
        description="Mapping of changeling name to backend URL",
    )

    def get_backend_url(self, changeling_name: ChangelingName) -> str | None:
        return self.url_by_changeling_name.get(str(changeling_name))

    def list_known_changeling_names(self) -> tuple[ChangelingName, ...]:
        return tuple(ChangelingName(name) for name in sorted(self.url_by_changeling_name.keys()))
