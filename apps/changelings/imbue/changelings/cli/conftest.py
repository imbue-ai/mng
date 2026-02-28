import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pytest

from imbue.mng.utils.testing import isolate_home


@pytest.fixture(autouse=True)
def isolate_changeling_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Isolate changeling CLI tests from the real mng environment.

    Sets HOME, MNG_HOST_DIR, and MNG_PREFIX to temp/unique values so that
    tests do not create agents in the real ~/.mng or pollute the real tmux
    server. Also isolates the tmux server so test sessions don't interfere
    with the user's real tmux.
    """
    test_id = uuid4().hex
    host_dir = tmp_path / ".mng"
    host_dir.mkdir()

    isolate_home(tmp_path, monkeypatch)
    monkeypatch.setenv("MNG_HOST_DIR", str(host_dir))
    monkeypatch.setenv("MNG_PREFIX", "mng_{}-".format(test_id))
    monkeypatch.setenv("MNG_ROOT_NAME", "mng-test-{}".format(test_id))
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(host_dir))

    # Isolate tmux server so test sessions don't touch the real one
    tmux_tmpdir = Path(tempfile.mkdtemp(prefix="mng-tmux-", dir="/tmp"))
    monkeypatch.setenv("TMUX_TMPDIR", str(tmux_tmpdir))
    monkeypatch.delenv("TMUX", raising=False)

    # Create .gitconfig so git commands work in the temp HOME
    gitconfig = tmp_path / ".gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text("[user]\n\tname = Test User\n\temail = test@test.com\n")

    yield

    # Kill the isolated tmux server
    tmux_tmpdir_str = str(tmux_tmpdir)
    if tmux_tmpdir_str.startswith("/tmp/mng-tmux-"):
        socket_path = Path(tmux_tmpdir_str) / "tmux-{}".format(os.getuid()) / "default"
        kill_env = os.environ.copy()
        kill_env.pop("TMUX", None)
        kill_env["TMUX_TMPDIR"] = tmux_tmpdir_str
        subprocess.run(
            ["tmux", "-S", str(socket_path), "kill-server"],
            capture_output=True,
            env=kill_env,
        )
    shutil.rmtree(tmux_tmpdir, ignore_errors=True)
