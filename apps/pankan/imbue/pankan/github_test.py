import json
from unittest.mock import MagicMock

from imbue.concurrency_group.errors import ProcessError
from imbue.pankan.data_types import CheckStatus
from imbue.pankan.data_types import PrState
from imbue.pankan.github import _parse_check_status
from imbue.pankan.github import _parse_pr
from imbue.pankan.github import _parse_pr_state
from imbue.pankan.github import fetch_all_prs

# === _parse_pr_state ===


def test_parse_pr_state_open() -> None:
    assert _parse_pr_state("OPEN") == PrState.OPEN


def test_parse_pr_state_closed() -> None:
    assert _parse_pr_state("CLOSED") == PrState.CLOSED


def test_parse_pr_state_merged() -> None:
    assert _parse_pr_state("MERGED") == PrState.MERGED


def test_parse_pr_state_lowercase() -> None:
    assert _parse_pr_state("open") == PrState.OPEN
    assert _parse_pr_state("closed") == PrState.CLOSED
    assert _parse_pr_state("merged") == PrState.MERGED


def test_parse_pr_state_unknown_defaults_to_open() -> None:
    assert _parse_pr_state("DRAFT") == PrState.OPEN


# === _parse_check_status ===


def test_parse_check_status_none() -> None:
    assert _parse_check_status(None) == CheckStatus.UNKNOWN


def test_parse_check_status_empty_list() -> None:
    assert _parse_check_status([]) == CheckStatus.UNKNOWN


def test_parse_check_status_all_success() -> None:
    rollup = [
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
    ]
    assert _parse_check_status(rollup) == CheckStatus.PASSING


def test_parse_check_status_any_failure() -> None:
    rollup = [
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "COMPLETED", "conclusion": "FAILURE"},
    ]
    assert _parse_check_status(rollup) == CheckStatus.FAILING


def test_parse_check_status_error_conclusion() -> None:
    rollup = [{"status": "COMPLETED", "conclusion": "ERROR"}]
    assert _parse_check_status(rollup) == CheckStatus.FAILING


def test_parse_check_status_cancelled_conclusion() -> None:
    rollup = [{"status": "COMPLETED", "conclusion": "CANCELLED"}]
    assert _parse_check_status(rollup) == CheckStatus.FAILING


def test_parse_check_status_timed_out_conclusion() -> None:
    rollup = [{"status": "COMPLETED", "conclusion": "TIMED_OUT"}]
    assert _parse_check_status(rollup) == CheckStatus.FAILING


def test_parse_check_status_action_required_conclusion() -> None:
    rollup = [{"status": "COMPLETED", "conclusion": "ACTION_REQUIRED"}]
    assert _parse_check_status(rollup) == CheckStatus.FAILING


def test_parse_check_status_pending() -> None:
    rollup = [
        {"status": "COMPLETED", "conclusion": "SUCCESS"},
        {"status": "IN_PROGRESS", "conclusion": None},
    ]
    assert _parse_check_status(rollup) == CheckStatus.PENDING


def test_parse_check_status_queued() -> None:
    rollup = [{"status": "QUEUED", "conclusion": None}]
    assert _parse_check_status(rollup) == CheckStatus.PENDING


def test_parse_check_status_failure_takes_priority_over_pending() -> None:
    rollup = [
        {"status": "IN_PROGRESS", "conclusion": None},
        {"status": "COMPLETED", "conclusion": "FAILURE"},
    ]
    assert _parse_check_status(rollup) == CheckStatus.FAILING


# === _parse_pr ===


def test_parse_pr() -> None:
    raw = {
        "number": 42,
        "title": "Add feature X",
        "state": "OPEN",
        "url": "https://github.com/org/repo/pull/42",
        "headRefName": "mng/my-agent-local",
        "statusCheckRollup": [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
        ],
    }
    pr = _parse_pr(raw)
    assert pr.number == 42
    assert pr.title == "Add feature X"
    assert pr.state == PrState.OPEN
    assert pr.url == "https://github.com/org/repo/pull/42"
    assert pr.head_branch == "mng/my-agent-local"
    assert pr.check_status == CheckStatus.PASSING


def test_parse_pr_merged_with_no_checks() -> None:
    raw = {
        "number": 10,
        "title": "Fix bug",
        "state": "MERGED",
        "url": "https://github.com/org/repo/pull/10",
        "headRefName": "mng/fix-bug-local",
        "statusCheckRollup": [],
    }
    pr = _parse_pr(raw)
    assert pr.state == PrState.MERGED
    assert pr.check_status == CheckStatus.UNKNOWN


# === fetch_all_prs ===


def _make_mock_cg(stdout: str) -> MagicMock:
    """Create a mock ConcurrencyGroup that returns the given stdout."""
    cg = MagicMock()
    result = MagicMock()
    result.stdout = stdout
    cg.run_process_to_completion.return_value = result
    return cg


def test_fetch_all_prs_success() -> None:
    raw_prs = [
        {
            "number": 1,
            "title": "PR 1",
            "state": "OPEN",
            "url": "https://github.com/org/repo/pull/1",
            "headRefName": "branch-1",
            "statusCheckRollup": [],
        },
        {
            "number": 2,
            "title": "PR 2",
            "state": "MERGED",
            "url": "https://github.com/org/repo/pull/2",
            "headRefName": "branch-2",
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
        },
    ]
    cg = _make_mock_cg(json.dumps(raw_prs))
    prs = fetch_all_prs(cg)
    assert len(prs) == 2
    assert prs[0].number == 1
    assert prs[0].state == PrState.OPEN
    assert prs[1].number == 2
    assert prs[1].state == PrState.MERGED


def test_fetch_all_prs_process_error() -> None:
    cg = MagicMock()
    cg.run_process_to_completion.side_effect = ProcessError(
        command=("gh", "pr", "list"),
        returncode=1,
        stdout="",
        stderr="gh: not found",
    )
    prs = fetch_all_prs(cg)
    assert prs == ()


def test_fetch_all_prs_invalid_json() -> None:
    cg = _make_mock_cg("not valid json")
    prs = fetch_all_prs(cg)
    assert prs == ()


def test_fetch_all_prs_empty_list() -> None:
    cg = _make_mock_cg("[]")
    prs = fetch_all_prs(cg)
    assert prs == ()
