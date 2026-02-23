import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    """Write content to a file atomically using a temp file and rename.

    Writes to a temporary file in the same directory, flushes to disk with
    fsync, then atomically replaces the target file. This ensures readers
    never see a partially-written file, even after power loss.

    Note: NamedTemporaryFile creates files with 0600 permissions, and
    os.replace preserves those, so the target file may end up with different
    permissions than the original. 0600 is reasonable for most files, but
    could be an issue if something expects group/other-readable permissions.

    The caller is responsible for catching OSError if the write fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as tmp_file:
        tmp_file.write(content)
        tmp_file.flush()
        os.fsync(tmp_file.fileno())
        tmp_path = Path(tmp_file.name)

    try:
        os.replace(tmp_path, path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
