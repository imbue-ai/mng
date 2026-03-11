"""Unit tests for test-mapreduce API functions."""

from pathlib import Path

import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.primitives import AgentName
from imbue.mng_test_mapreduce.api import CollectTestsError
from imbue.mng_test_mapreduce.api import PLUGIN_NAME
from imbue.mng_test_mapreduce.api import _build_agent_prompt
from imbue.mng_test_mapreduce.api import _html_escape
from imbue.mng_test_mapreduce.api import _sanitize_test_name_for_agent
from imbue.mng_test_mapreduce.api import collect_tests
from imbue.mng_test_mapreduce.api import generate_html_report
from imbue.mng_test_mapreduce.data_types import TestMapReduceResult
from imbue.mng_test_mapreduce.data_types import TestOutcome

# --- _sanitize_test_name_for_agent ---


def test_sanitize_simple_test_name() -> None:
    assert _sanitize_test_name_for_agent("tests/test_foo.py::test_bar") == "test-bar"


def test_sanitize_nested_test_name() -> None:
    assert _sanitize_test_name_for_agent("tests/test_foo.py::TestClass::test_method") == "test-method"


def test_sanitize_parametrized_test_name() -> None:
    result = _sanitize_test_name_for_agent("tests/test_foo.py::test_bar[param1-param2]")
    assert result == "test-bar-param1-param2-"[:40].rstrip("-")


def test_sanitize_truncates_long_names() -> None:
    long_name = "tests/test_foo.py::test_" + "a" * 100
    result = _sanitize_test_name_for_agent(long_name)
    assert len(result) <= 40


def test_sanitize_special_characters() -> None:
    result = _sanitize_test_name_for_agent("tests/test_foo.py::test_with spaces_and___underscores")
    assert " " not in result
    assert "--" not in result


def test_sanitize_single_part() -> None:
    result = _sanitize_test_name_for_agent("simple_test")
    assert result == "simple-test"


# --- _build_agent_prompt ---


def test_build_agent_prompt_contains_test_id() -> None:
    prompt = _build_agent_prompt("tests/test_foo.py::test_bar")
    assert "tests/test_foo.py::test_bar" in prompt
    assert "RUN_SUCCEEDED" in prompt
    assert "FIX_TEST_SUCCEEDED" in prompt
    assert "FIX_IMPL_SUCCEEDED" in prompt
    assert "FIX_UNCERTAIN" in prompt
    assert "result.json" in prompt


def test_build_agent_prompt_contains_plugin_name() -> None:
    prompt = _build_agent_prompt("tests/test_x.py::test_y")
    assert PLUGIN_NAME in prompt


# --- _html_escape ---


def test_html_escape() -> None:
    assert _html_escape("<script>") == "&lt;script&gt;"
    assert _html_escape('a & "b"') == "a &amp; &quot;b&quot;"


def test_html_escape_no_change() -> None:
    assert _html_escape("plain text") == "plain text"


# --- collect_tests ---


def test_collect_tests_with_real_pytest(tmp_path: Path, cg: ConcurrencyGroup) -> None:
    """Use a real pytest --collect-only against a tiny test file."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text("def test_one(): pass\ndef test_two(): pass\n")

    test_ids = collect_tests(
        pytest_args=(str(test_file),),
        source_dir=tmp_path,
        cg=cg,
    )

    assert len(test_ids) == 2
    assert any("test_one" in tid for tid in test_ids)
    assert any("test_two" in tid for tid in test_ids)


def test_collect_tests_no_tests_raises(tmp_path: Path, cg: ConcurrencyGroup) -> None:
    """Empty directory has no tests."""
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("x = 1\n")
    with pytest.raises(CollectTestsError):
        collect_tests(
            pytest_args=(str(empty_file),),
            source_dir=tmp_path,
            cg=cg,
        )


def test_collect_tests_bad_file_raises(tmp_path: Path, cg: ConcurrencyGroup) -> None:
    """Non-existent file triggers collection failure."""
    with pytest.raises(CollectTestsError):
        collect_tests(
            pytest_args=("non_existent_test_file.py",),
            source_dir=tmp_path,
            cg=cg,
        )


# --- generate_html_report ---


def test_generate_html_report(tmp_path: Path) -> None:
    results = [
        TestMapReduceResult(
            test_node_id="tests/test_a.py::test_pass",
            agent_name=AgentName("tmr-test-pass"),
            outcome=TestOutcome.RUN_SUCCEEDED,
            summary="Passed immediately",
        ),
        TestMapReduceResult(
            test_node_id="tests/test_b.py::test_fixed",
            agent_name=AgentName("tmr-test-fixed"),
            outcome=TestOutcome.FIX_IMPL_SUCCEEDED,
            summary="Fixed missing import",
            branch_name="mng-tmr/test-fixed",
        ),
        TestMapReduceResult(
            test_node_id="tests/test_c.py::test_uncertain",
            agent_name=AgentName("tmr-test-uncertain"),
            outcome=TestOutcome.FIX_UNCERTAIN,
            summary="Could not determine root cause",
        ),
    ]

    output_path = tmp_path / "report.html"
    result_path = generate_html_report(results, output_path)

    assert result_path == output_path
    assert output_path.exists()

    content = output_path.read_text()
    assert "Test Map-Reduce Report" in content
    assert "tests/test_a.py::test_pass" in content
    assert "RUN_SUCCEEDED" in content
    assert "FIX_IMPL_SUCCEEDED" in content
    assert "FIX_UNCERTAIN" in content
    assert "mng-tmr/test-fixed" in content
    assert "3 test(s)" in content


def test_generate_html_report_escapes_html(tmp_path: Path) -> None:
    results = [
        TestMapReduceResult(
            test_node_id="tests/test_<xss>.py::test_inject",
            agent_name=AgentName("tmr-test-inject"),
            outcome=TestOutcome.RUN_SUCCEEDED,
            summary='<script>alert("xss")</script>',
        ),
    ]

    output_path = tmp_path / "report.html"
    generate_html_report(results, output_path)
    content = output_path.read_text()

    assert "<script>" not in content
    assert "&lt;script&gt;" in content


def test_generate_html_report_creates_parent_dirs(tmp_path: Path) -> None:
    output_path = tmp_path / "subdir" / "nested" / "report.html"
    results = [
        TestMapReduceResult(
            test_node_id="tests/test.py::test_x",
            agent_name=AgentName("tmr-test-x"),
            outcome=TestOutcome.RUN_SUCCEEDED,
            summary="ok",
        ),
    ]
    generate_html_report(results, output_path)
    assert output_path.exists()


def test_generate_html_report_all_outcomes(tmp_path: Path) -> None:
    """Every outcome type renders without error."""
    results = [
        TestMapReduceResult(
            test_node_id=f"t::test_{outcome.name.lower()}",
            agent_name=AgentName(f"tmr-{outcome.name.lower()}"),
            outcome=outcome,
            summary=f"Summary for {outcome.value}",
        )
        for outcome in TestOutcome
    ]
    output_path = tmp_path / "all_outcomes.html"
    generate_html_report(results, output_path)
    content = output_path.read_text()
    for outcome in TestOutcome:
        assert outcome.value in content


def test_generate_html_report_empty_results(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.html"
    generate_html_report([], output_path)
    content = output_path.read_text()
    assert "0 test(s)" in content
