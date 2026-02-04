from __future__ import annotations

import platform
from typing import Final

from imbue.imbue_common.errors import SwitchError
from imbue.imbue_common.pure import pure
from imbue.mngr.primitives import ActivitySource
from imbue.mngr.primitives import IdleMode

LOCAL_CONNECTOR_NAME: Final[str] = "LocalConnector"


@pure
def is_macos() -> bool:
    """Check if the current system is macOS (Darwin)."""
    return platform.system() == "Darwin"


# Activity sources that are host-level (vs agent-level)
HOST_LEVEL_ACTIVITY_SOURCES: Final[frozenset[ActivitySource]] = frozenset(
    {
        ActivitySource.BOOT,
        ActivitySource.USER,
        ActivitySource.SSH,
    }
)


def get_activity_sources_for_idle_mode(idle_mode: IdleMode) -> tuple[ActivitySource, ...]:
    """Get the activity sources that should be monitored for a given idle mode.

    This mapping is defined in docs/concepts/idle_detection.md.
    """
    if idle_mode == IdleMode.IO:
        return (
            ActivitySource.USER,
            ActivitySource.AGENT,
            ActivitySource.SSH,
            ActivitySource.CREATE,
            ActivitySource.START,
            ActivitySource.BOOT,
        )
    elif idle_mode == IdleMode.USER:
        return (
            ActivitySource.USER,
            ActivitySource.SSH,
            ActivitySource.CREATE,
            ActivitySource.START,
            ActivitySource.BOOT,
        )
    elif idle_mode == IdleMode.AGENT:
        return (
            ActivitySource.AGENT,
            ActivitySource.SSH,
            ActivitySource.CREATE,
            ActivitySource.START,
            ActivitySource.BOOT,
        )
    elif idle_mode == IdleMode.SSH:
        return (
            ActivitySource.SSH,
            ActivitySource.CREATE,
            ActivitySource.START,
            ActivitySource.BOOT,
        )
    elif idle_mode == IdleMode.CREATE:
        return (ActivitySource.CREATE,)
    elif idle_mode == IdleMode.BOOT:
        return (ActivitySource.BOOT,)
    elif idle_mode == IdleMode.START:
        return (ActivitySource.START, ActivitySource.BOOT)
    elif idle_mode == IdleMode.RUN:
        return (
            ActivitySource.CREATE,
            ActivitySource.START,
            ActivitySource.BOOT,
            ActivitySource.PROCESS,
        )
    elif idle_mode == IdleMode.DISABLED:
        return ()
    else:
        raise SwitchError(idle_mode)
