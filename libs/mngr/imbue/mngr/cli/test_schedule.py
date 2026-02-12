import json
import os
import stat
from pathlib import Path
from typing import Generator
from uuid import uuid4

import pytest
from click.testing import CliRunner

from imbue.mngr.main import cli

# Fake crontab script that stores its data in $HOME/.fake_crontab.
# Supports `crontab -l` (list) and `crontab <file>` (install from file).
_FAKE_CRONTAB_SCRIPT = """\
#!/bin/sh
CRONTAB_FILE="$HOME/.fake_crontab"
if [ "$1" = "-l" ]; then
    if [ -f "$CRONTAB_FILE" ]; then
        cat "$CRONTAB_FILE"
    else
        echo "no crontab for $(whoami)" >&2
        exit 1
    fi
elif [ -f "$1" ]; then
    cp "$1" "$CRONTAB_FILE"
else
    echo "usage: crontab [-l | file]" >&2
    exit 1
fi
"""


@pytest.fixture(autouse=True)
def fake_crontab(tmp_home_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Install a fake crontab binary that reads/writes a file under $HOME.

    The real crontab modifies per-user system state that cannot be sandboxed
    via HOME alone, and may require special permissions on macOS. This fake
    binary shadows the real one on PATH and stores data in $HOME/.fake_crontab,
    which is already sandboxed by the autouse setup_test_mngr_env fixture.
    """
    bin_dir = tmp_home_dir / "bin"
    bin_dir.mkdir(exist_ok=True)
    crontab_script = bin_dir / "crontab"
    crontab_script.write_text(_FAKE_CRONTAB_SCRIPT)
    crontab_script.chmod(crontab_script.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    yield tmp_home_dir / ".fake_crontab"


def _read_fake_crontab(fake_crontab_path: Path) -> str:
    if fake_crontab_path.exists():
        return fake_crontab_path.read_text()
    return ""


def test_schedule_add_creates_schedule_and_installs_crontab(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    fake_crontab: Path,
) -> None:
    name = f"sched-{uuid4().hex[:8]}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "fix tests"],
    )

    assert result.exit_code == 0, result.output
    assert f"Added schedule '{name}'" in result.output

    crontab_content = _read_fake_crontab(fake_crontab)
    assert f"mngr-schedule:{name}" in crontab_content
    assert "fix tests" in crontab_content


def test_schedule_add_with_template(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    fake_crontab: Path,
) -> None:
    name = f"sched-tpl-{uuid4().hex[:8]}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "*/5 * * * *", "--template", "my-hook", "--name", name, "run hook"],
    )

    assert result.exit_code == 0, result.output
    assert f"Added schedule '{name}'" in result.output
    assert "--template" in result.output

    crontab_content = _read_fake_crontab(fake_crontab)
    assert "--template my-hook" in crontab_content


def test_schedule_add_rejects_invalid_cron(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-bad-{uuid4().hex[:8]}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "not-a-cron", "--name", name, "test"],
    )

    assert result.exit_code != 0
    assert "Invalid cron expression" in result.output


def test_schedule_add_rejects_duplicate_name(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-dup-{uuid4().hex[:8]}"

    result1 = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "first"],
    )
    assert result1.exit_code == 0, result1.output

    result2 = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "second"],
    )
    assert result2.exit_code != 0
    assert "already exists" in result2.output


def test_schedule_list_shows_schedules(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-list-{uuid4().hex[:8]}"

    cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "fix tests"],
    )

    result = cli_runner.invoke(cli, ["schedule", "list"])
    assert result.exit_code == 0, result.output
    assert name in result.output
    assert "fix tests" in result.output


def test_schedule_list_empty(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    result = cli_runner.invoke(cli, ["schedule", "list"])
    assert result.exit_code == 0, result.output
    assert "No schedules configured" in result.output


def test_schedule_list_json_format(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-json-{uuid4().hex[:8]}"

    cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "json test"],
    )

    result = cli_runner.invoke(cli, ["schedule", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "schedules" in data
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["name"] == name


def test_schedule_remove_removes_schedule_and_crontab_entry(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    fake_crontab: Path,
) -> None:
    name = f"sched-rm-{uuid4().hex[:8]}"

    cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "to remove"],
    )

    assert f"mngr-schedule:{name}" in _read_fake_crontab(fake_crontab)

    result = cli_runner.invoke(cli, ["schedule", "remove", name])

    assert result.exit_code == 0, result.output
    assert f"Removed schedule '{name}'" in result.output

    list_result = cli_runner.invoke(cli, ["schedule", "list"])
    assert name not in list_result.output

    assert f"mngr-schedule:{name}" not in _read_fake_crontab(fake_crontab)


def test_schedule_remove_nonexistent_fails(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    result = cli_runner.invoke(cli, ["schedule", "remove", "nonexistent"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_schedule_shows_help_when_no_subcommand(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.invoke(cli, ["schedule"])
    assert result.exit_code == 0
    assert "Manage scheduled agents" in result.output


def test_schedule_add_json_format(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-addjson-{uuid4().hex[:8]}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "--format", "json", "json add test"],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == name
    assert data["cron"] == "0 * * * *"
    assert "crontab_line" in data


def test_schedule_add_then_remove_preserves_other_crontab_entries(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    fake_crontab: Path,
) -> None:
    name_a = f"sched-a-{uuid4().hex[:8]}"
    name_b = f"sched-b-{uuid4().hex[:8]}"

    cli_runner.invoke(cli, ["schedule", "add", "--cron", "0 * * * *", "--name", name_a, "task a"])
    cli_runner.invoke(cli, ["schedule", "add", "--cron", "*/5 * * * *", "--name", name_b, "task b"])

    crontab_content = _read_fake_crontab(fake_crontab)
    assert f"mngr-schedule:{name_a}" in crontab_content
    assert f"mngr-schedule:{name_b}" in crontab_content

    cli_runner.invoke(cli, ["schedule", "remove", name_a])

    crontab_after = _read_fake_crontab(fake_crontab)
    assert f"mngr-schedule:{name_a}" not in crontab_after
    assert f"mngr-schedule:{name_b}" in crontab_after
