import json
from unittest.mock import patch

import pytest

from imbue.slack_exporter.errors import LatchkeyInvocationError
from imbue.slack_exporter.errors import SlackApiError
from imbue.slack_exporter.latchkey import call_slack_api


class _FakeCompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestCallSlackApi:
    def test_successful_call(self) -> None:
        response_data = {"ok": True, "channels": []}
        fake_result = _FakeCompletedProcess(returncode=0, stdout=json.dumps(response_data))

        with patch("imbue.slack_exporter.latchkey.subprocess.run", return_value=fake_result):
            result = call_slack_api("conversations.list")

        assert result == response_data

    def test_with_query_params(self) -> None:
        response_data = {"ok": True, "messages": []}
        fake_result = _FakeCompletedProcess(returncode=0, stdout=json.dumps(response_data))

        with patch("imbue.slack_exporter.latchkey.subprocess.run", return_value=fake_result) as mock_run:
            call_slack_api("conversations.history", query_params={"channel": "C123", "limit": "10"})

        called_url = mock_run.call_args[0][0][2]
        assert "conversations.history?" in called_url
        assert "channel=C123" in called_url

    def test_raises_on_nonzero_exit(self) -> None:
        fake_result = _FakeCompletedProcess(returncode=1, stdout="", stderr="auth failed")

        with (
            patch("imbue.slack_exporter.latchkey.subprocess.run", return_value=fake_result),
            pytest.raises(LatchkeyInvocationError, match="exit 1"),
        ):
            call_slack_api("conversations.list")

    def test_raises_on_invalid_json(self) -> None:
        fake_result = _FakeCompletedProcess(returncode=0, stdout="not json")

        with (
            patch("imbue.slack_exporter.latchkey.subprocess.run", return_value=fake_result),
            pytest.raises(LatchkeyInvocationError, match="Invalid JSON"),
        ):
            call_slack_api("conversations.list")

    def test_raises_on_slack_api_error(self) -> None:
        response_data = {"ok": False, "error": "channel_not_found"}
        fake_result = _FakeCompletedProcess(returncode=0, stdout=json.dumps(response_data))

        with (
            patch("imbue.slack_exporter.latchkey.subprocess.run", return_value=fake_result),
            pytest.raises(SlackApiError, match="channel_not_found"),
        ):
            call_slack_api("conversations.history")
