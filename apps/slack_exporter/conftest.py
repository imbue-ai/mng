from pathlib import Path

import pytest

from imbue.imbue_common.conftest_hooks import register_conftest_hooks

register_conftest_hooks(globals())


@pytest.fixture()
def temp_output_dir(tmp_path: Path) -> Path:
    return tmp_path / "slack_export"
