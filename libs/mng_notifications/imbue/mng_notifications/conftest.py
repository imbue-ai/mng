from typing import Any

import pytest


@pytest.fixture()
def fake_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Monkeypatch subprocess.run in the notifier module and return the captured call args."""
    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **kwargs: Any) -> None:
        calls.append(cmd)

    monkeypatch.setattr("imbue.mng_notifications.notifier.subprocess.run", _fake_run)
    return calls
