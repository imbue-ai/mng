import shutil

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr.errors import BinaryNotInstalledError


class SystemDependency(FrozenModel):
    """A system binary that mngr requires at runtime."""

    binary: str = Field(description="Name of the binary on PATH")
    purpose: str = Field(description="What this binary is used for")
    install_hint: str = Field(description="Human-readable installation instructions")

    def is_available(self) -> bool:
        """Check if this binary is available on PATH."""
        return shutil.which(self.binary) is not None

    def require(self) -> None:
        """Raise BinaryNotInstalledError if this binary is not available."""
        if not self.is_available():
            raise BinaryNotInstalledError(self.binary, self.purpose, self.install_hint)


RSYNC = SystemDependency(
    binary="rsync",
    purpose="file sync",
    install_hint="On macOS: brew install rsync. On Linux: sudo apt-get install rsync.",
)

TMUX = SystemDependency(
    binary="tmux",
    purpose="agent session management",
    install_hint="On macOS: brew install tmux. On Linux: sudo apt-get install tmux.",
)

GIT = SystemDependency(
    binary="git",
    purpose="source control",
    install_hint="On macOS: brew install git. On Linux: sudo apt-get install git.",
)

JQ = SystemDependency(
    binary="jq",
    purpose="JSON processing",
    install_hint="On macOS: brew install jq. On Linux: sudo apt-get install jq.",
)
