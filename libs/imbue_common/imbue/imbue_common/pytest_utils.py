import pytest

from imbue.imbue_common.pure import pure


@pure
def inline_snapshot_is_updating(config: pytest.Config) -> bool:
    """Check if inline-snapshot is running with create or fix flags.

    This is useful for tests that need to behave differently when snapshots
    are being created or fixed vs when they are being validated.
    """
    inline_snapshot_flags = config.option.inline_snapshot
    if inline_snapshot_flags is None:
        return False

    flags = inline_snapshot_flags.split(",")
    return "create" in flags or "fix" in flags
