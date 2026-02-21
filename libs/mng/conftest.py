"""Project-level conftest for mng.

When running tests from libs/mng/, this conftest provides the common pytest hooks
that would otherwise come from the monorepo root conftest.py (which is not discovered
when pytest runs from a subdirectory).

When running from the monorepo root, the root conftest.py registers the hooks first,
and this file's register_conftest_hooks() call is a no-op (guarded by a module-level flag).
"""

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.mng.utils.logging import suppress_warnings

suppress_warnings()
register_conftest_hooks(globals())

# Register fixture modules so pytest discovers fixtures defined in fixtures.py files.
# This must be in a top-level conftest.py (pytest disallows pytest_plugins in
# non-top-level conftest files).
pytest_plugins = [
    "imbue.mng.fixtures",
    "imbue.mng.cli.fixtures",
    "imbue.mng.providers.modal.fixtures",
]
