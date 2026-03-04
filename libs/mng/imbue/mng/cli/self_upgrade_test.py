import json
from unittest.mock import patch

import pytest

from imbue.mng.cli.output_helpers import AbortError
from imbue.mng.cli.self_upgrade import _emit_self_upgrade_result
from imbue.mng.cli.self_upgrade import _require_uv_tool_for_self_upgrade
from imbue.mng.config.data_types import OutputOptions
from imbue.mng.primitives import OutputFormat

# =============================================================================
# Tests for _require_uv_tool_for_self_upgrade
# =============================================================================


def test_require_uv_tool_for_self_upgrade_raises_when_no_receipt() -> None:
    """_require_uv_tool_for_self_upgrade should raise AbortError when no receipt exists."""
    with patch("imbue.mng.cli.self_upgrade.get_receipt_path", return_value=None):
        with pytest.raises(AbortError, match="not installed via 'uv tool install'"):
            _require_uv_tool_for_self_upgrade()


def test_require_uv_tool_for_self_upgrade_succeeds_when_receipt_exists(tmp_path: pytest.TempPathFactory) -> None:
    """_require_uv_tool_for_self_upgrade should not raise when a receipt exists."""
    fake_receipt = tmp_path / "uv-receipt.toml"  # type: ignore[operator]
    fake_receipt.write_text("")
    with patch("imbue.mng.cli.self_upgrade.get_receipt_path", return_value=fake_receipt):
        _require_uv_tool_for_self_upgrade()


# =============================================================================
# Tests for _emit_self_upgrade_result
# =============================================================================


def test_emit_self_upgrade_result_human_with_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_self_upgrade_result should print stdout in HUMAN format."""
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    _emit_self_upgrade_result("Updated mng v1.0.0 -> v1.1.0", output_opts)

    captured = capsys.readouterr()
    assert "Updated mng v1.0.0 -> v1.1.0" in captured.out


def test_emit_self_upgrade_result_human_no_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_self_upgrade_result should print a default message when stdout is empty."""
    output_opts = OutputOptions(output_format=OutputFormat.HUMAN)
    _emit_self_upgrade_result("", output_opts)

    captured = capsys.readouterr()
    assert "mng upgraded successfully" in captured.out


def test_emit_self_upgrade_result_json(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_self_upgrade_result should output valid JSON."""
    output_opts = OutputOptions(output_format=OutputFormat.JSON)
    _emit_self_upgrade_result("Updated mng v1.0.0 -> v1.1.0", output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["upgraded"] is True
    assert data["message"] == "Updated mng v1.0.0 -> v1.1.0"


def test_emit_self_upgrade_result_jsonl(capsys: pytest.CaptureFixture[str]) -> None:
    """_emit_self_upgrade_result should output JSONL with event type."""
    output_opts = OutputOptions(output_format=OutputFormat.JSONL)
    _emit_self_upgrade_result("Updated mng v1.0.0 -> v1.1.0", output_opts)

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())
    assert data["event"] == "self_upgraded"
    assert data["message"] == "Updated mng v1.0.0 -> v1.1.0"
