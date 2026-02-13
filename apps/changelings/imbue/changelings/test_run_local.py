# Integration test for running a changeling locally via the CLI.
#
# This test verifies the end-to-end flow of running a changeling in local mode
# by specifying all necessary arguments on the command line (without needing
# a config entry first).

from pathlib import Path

import pytest
from click.testing import CliRunner

from imbue.changelings.cli.run import run


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate config operations to a temporary home directory."""
    monkeypatch.setenv("HOME", str(tmp_path))


def test_run_local_with_cli_args_without_config() -> None:
    """Running locally with CLI args should work without a config entry.

    Verifies the full flow: the run command constructs a ChangelingDefinition
    from CLI arguments (no config lookup needed), builds the mngr create
    command, and executes it successfully.
    """
    runner = CliRunner()
    result = runner.invoke(
        run,
        [
            "test-direct-run",
            "--local",
            "--agent-type",
            "code-guardian",
        ],
    )

    assert result.exit_code == 0, f"Expected exit code 0, got {result.exit_code}. Output: {result.output}"
