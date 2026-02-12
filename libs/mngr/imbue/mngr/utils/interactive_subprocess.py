import subprocess
from collections.abc import Sequence
from typing import Any


def run_interactive_subprocess(
    command: Sequence[str],
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run a subprocess that requires interactive terminal access.

    These bypass ConcurrencyGroup because they need direct terminal control
    (stdin/stdout/stderr passthrough to the user's terminal).
    """
    return subprocess.run(command, **kwargs)


def popen_interactive_subprocess(
    command: Sequence[str],
    **kwargs: Any,
) -> subprocess.Popen[Any]:
    """Open a subprocess that requires interactive terminal access.

    These bypass ConcurrencyGroup because they need direct terminal control
    (stdin/stdout/stderr passthrough to the user's terminal).
    """
    return subprocess.Popen(command, **kwargs)
