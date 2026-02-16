"""Test to verify whether coverage captures subprocess invocations via 'uv run'."""

import subprocess
import textwrap

import pytest


@pytest.mark.xfail(
    reason="Subprocess coverage is not configured. See https://coverage.readthedocs.io/en/latest/subprocess.html",
    strict=True,
)
def test_uv_run_subprocess_coverage_is_active() -> None:
    """Check if coverage measurement is active in 'uv run' subprocesses.

    When tests invoke 'uv run mngr <command>' via subprocess, the code in that
    subprocess should be measured by coverage. This requires either:
    - COVERAGE_PROCESS_START env var set to a coverage config file path, or
    - COV_CORE_SOURCE env var (set by pytest-cov)
    AND a .pth file in site-packages that calls coverage.process_startup().

    The .pth file exists (a1_coverage.pth), but it only activates when
    COVERAGE_PROCESS_START or COVERAGE_PROCESS_CONFIG is set. Neither pytest-cov
    nor our test infrastructure sets these env vars for subprocess calls, so
    coverage data from 'uv run mngr ...' invocations is silently lost.

    See: https://coverage.readthedocs.io/en/latest/subprocess.html
    """
    check_script = textwrap.dedent("""\
        import sys, os
        active = False
        # coverage 7.4+ on Python 3.12+ uses sys.monitoring
        if hasattr(sys, 'monitoring'):
            tool = sys.monitoring.get_tool(sys.monitoring.COVERAGE_ID)
            if tool is not None:
                active = True
        # Older versions use sys.settrace
        if not active and sys.gettrace() is not None:
            active = True
        print('COVERED' if active else 'NOT_COVERED')
    """)

    result = subprocess.run(
        ["uv", "run", "python", "-c", check_script],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
    first_line = result.stdout.strip().splitlines()[0]
    assert first_line == "COVERED", (
        "Coverage is NOT active in 'uv run' subprocesses. "
        "Code executed via subprocess.run(['uv', 'run', ...]) is not being measured by coverage."
    )
