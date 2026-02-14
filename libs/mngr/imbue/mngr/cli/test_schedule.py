import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from imbue.mngr.main import cli


def _read_system_crontab() -> str:
    """Read the real system crontab. Returns empty string if none exists."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout


# === Integration tests (no crontab needed) ===


def test_schedule_shows_help_when_no_subcommand(
    cli_runner: CliRunner,
) -> None:
    result = cli_runner.invoke(cli, ["schedule", "-h"])
    assert result.exit_code == 0
    assert "Manage scheduled agents" in result.output


def test_schedule_list_empty(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    result = cli_runner.invoke(cli, ["schedule", "list"])
    assert result.exit_code == 0, result.output
    assert "No schedules configured" in result.output


def test_schedule_add_rejects_invalid_cron(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-bad-{uuid4().hex}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "not-a-cron", "--name", name, "test"],
    )

    assert result.exit_code != 0
    assert "Invalid cron expression" in result.output


def test_schedule_remove_nonexistent_fails(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    result = cli_runner.invoke(cli, ["schedule", "remove", "nonexistent"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# === Acceptance tests (require real crontab, e.g. on Modal) ===


@pytest.mark.acceptance
def test_schedule_add_creates_schedule_and_installs_crontab(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-{uuid4().hex}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "fix tests"],
    )

    assert result.exit_code == 0, result.output
    assert f"Added schedule '{name}'" in result.output

    crontab_content = _read_system_crontab()
    assert f"mngr-schedule:{name}" in crontab_content
    assert "fix tests" in crontab_content

    # Clean up: remove the crontab entry we just added
    cli_runner.invoke(cli, ["schedule", "remove", name])


@pytest.mark.acceptance
def test_schedule_add_with_template(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-tpl-{uuid4().hex}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "*/5 * * * *", "--template", "my-hook", "--name", name, "run hook"],
    )

    assert result.exit_code == 0, result.output
    assert f"Added schedule '{name}'" in result.output
    assert "--template" in result.output

    crontab_content = _read_system_crontab()
    assert "--template my-hook" in crontab_content

    # Clean up
    cli_runner.invoke(cli, ["schedule", "remove", name])


@pytest.mark.acceptance
def test_schedule_add_rejects_duplicate_name(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-dup-{uuid4().hex}"

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

    # Clean up
    cli_runner.invoke(cli, ["schedule", "remove", name])


@pytest.mark.acceptance
def test_schedule_list_shows_schedules(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-list-{uuid4().hex}"

    cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "fix tests"],
    )

    result = cli_runner.invoke(cli, ["schedule", "list"])
    assert result.exit_code == 0, result.output
    assert name in result.output
    assert "fix tests" in result.output

    # Clean up
    cli_runner.invoke(cli, ["schedule", "remove", name])


@pytest.mark.acceptance
def test_schedule_list_json_format(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-json-{uuid4().hex}"

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

    # Clean up
    cli_runner.invoke(cli, ["schedule", "remove", name])


@pytest.mark.acceptance
def test_schedule_remove_removes_schedule_and_crontab_entry(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-rm-{uuid4().hex}"

    cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "to remove"],
    )

    assert f"mngr-schedule:{name}" in _read_system_crontab()

    result = cli_runner.invoke(cli, ["schedule", "remove", name])

    assert result.exit_code == 0, result.output
    assert f"Removed schedule '{name}'" in result.output

    list_result = cli_runner.invoke(cli, ["schedule", "list"])
    assert name not in list_result.output

    assert f"mngr-schedule:{name}" not in _read_system_crontab()


@pytest.mark.acceptance
def test_schedule_add_json_format(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-addjson-{uuid4().hex}"

    result = cli_runner.invoke(
        cli,
        ["schedule", "add", "--cron", "0 * * * *", "--name", name, "--format", "json", "json add test"],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == name
    assert data["cron"] == "0 * * * *"
    assert "crontab_line" in data

    # Clean up
    cli_runner.invoke(cli, ["schedule", "remove", name])


@pytest.mark.acceptance
def test_schedule_add_then_remove_preserves_other_crontab_entries(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name_a = f"sched-a-{uuid4().hex}"
    name_b = f"sched-b-{uuid4().hex}"

    cli_runner.invoke(cli, ["schedule", "add", "--cron", "0 * * * *", "--name", name_a, "task a"])
    cli_runner.invoke(cli, ["schedule", "add", "--cron", "*/5 * * * *", "--name", name_b, "task b"])

    crontab_content = _read_system_crontab()
    assert f"mngr-schedule:{name_a}" in crontab_content
    assert f"mngr-schedule:{name_b}" in crontab_content

    cli_runner.invoke(cli, ["schedule", "remove", name_a])

    crontab_after = _read_system_crontab()
    assert f"mngr-schedule:{name_a}" not in crontab_after
    assert f"mngr-schedule:{name_b}" in crontab_after

    # Clean up
    cli_runner.invoke(cli, ["schedule", "remove", name_b])
