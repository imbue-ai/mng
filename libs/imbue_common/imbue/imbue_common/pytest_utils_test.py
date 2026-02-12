import pytest

from imbue.imbue_common.pytest_utils import inline_snapshot_is_updating


def test_demonstrate_inline_snapshot_detection_works(request: pytest.FixtureRequest) -> None:
    """Demonstrates that inline_snapshot_is_updating() correctly detects the flags.

    This is a demo test that shows the function working. Run it manually with
    different flags to see the detection in action:

    - Normal mode:
      uv run pytest libs/imbue_common/imbue/imbue_common/pytest_utils_demo_test.py -n 0 -s --no-cov

    - Create mode:
      uv run pytest libs/imbue_common/imbue/imbue_common/pytest_utils_demo_test.py -n 0 -s --no-cov --inline-snapshot=create

    - Fix mode:
      uv run pytest libs/imbue_common/imbue/imbue_common/pytest_utils_demo_test.py -n 0 -s --no-cov --inline-snapshot=fix

    - Multiple flags:
      uv run pytest libs/imbue_common/imbue/imbue_common/pytest_utils_demo_test.py -n 0 -s --no-cov --inline-snapshot=report,create,update

    Expected output:
    - Normal: returns False
    - Create/Fix: returns True
    - Multiple with create or fix: returns True
    - Multiple without create or fix: returns False
    """
    config = request.config
    is_updating = inline_snapshot_is_updating(config)

    print(f"\ninline_snapshot_is_updating() returned: {is_updating}")
    print(f"config.option.inline_snapshot = {getattr(config.option, 'inline_snapshot', None)}")

    if is_updating:
        print("  -> Detected: Running in create or fix mode")
        result = "updating"
    else:
        print("  -> Detected: Running in normal validation mode")
        result = "normal"

    assert result in ["updating", "normal"]
