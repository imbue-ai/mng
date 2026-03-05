from pathlib import Path

import pytest


@pytest.fixture()
def temp_output_path(tmp_path: Path) -> Path:
    return tmp_path / "slack_export.jsonl"
