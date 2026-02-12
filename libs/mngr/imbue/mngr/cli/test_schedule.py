"""Integration tests for the schedule command."""

import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from click.testing import CliRunner

from imbue.mngr.main import cli


def _make_crontab_noop() -> dict[str, str]:
    """Return patch targets for making crontab operations no-ops."""
    return {
        "read": "imbue.mngr.api.schedule._read_current_crontab",
        "write": "imbue.mngr.api.schedule._write_crontab",
    }


def test_schedule_add_creates_schedule_and_shows_output(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-{uuid4().hex[:8]}"
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]) as mock_write,
    ):
        result = cli_runner.invoke(
            cli,
            ["schedule", "add", "--cron", "0 * * * *", "--name", name, "fix tests"],
        )

    assert result.exit_code == 0, result.output
    assert f"Added schedule '{name}'" in result.output
    # crontab was written
    mock_write.assert_called_once()


def test_schedule_add_with_template(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-tpl-{uuid4().hex[:8]}"
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
        result = cli_runner.invoke(
            cli,
            ["schedule", "add", "--cron", "*/5 * * * *", "--template", "my-hook", "--name", name, "run hook"],
        )

    assert result.exit_code == 0, result.output
    assert f"Added schedule '{name}'" in result.output
    assert "--template" in result.output


def test_schedule_add_rejects_invalid_cron(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-bad-{uuid4().hex[:8]}"
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
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
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
        # First add should succeed
        result1 = cli_runner.invoke(
            cli,
            ["schedule", "add", "--cron", "0 * * * *", "--name", name, "first"],
        )
        assert result1.exit_code == 0, result1.output

        # Second add with same name should fail
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
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
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
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
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


def test_schedule_remove_removes_schedule(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    name = f"sched-rm-{uuid4().hex[:8]}"
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
        cli_runner.invoke(
            cli,
            ["schedule", "add", "--cron", "0 * * * *", "--name", name, "to remove"],
        )

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
        result = cli_runner.invoke(cli, ["schedule", "remove", name])

    assert result.exit_code == 0, result.output
    assert f"Removed schedule '{name}'" in result.output

    # Verify it's gone from the list
    list_result = cli_runner.invoke(cli, ["schedule", "list"])
    assert name not in list_result.output


def test_schedule_remove_nonexistent_fails(
    cli_runner: CliRunner,
    temp_host_dir: Path,
) -> None:
    targets = _make_crontab_noop()
    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
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
    targets = _make_crontab_noop()

    with (
        patch(targets["read"], return_value=""),
        patch(targets["write"]),
    ):
        result = cli_runner.invoke(
            cli,
            ["schedule", "add", "--cron", "0 * * * *", "--name", name, "--format", "json", "json add test"],
        )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["name"] == name
    assert data["cron"] == "0 * * * *"
    assert "crontab_line" in data
