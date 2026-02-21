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

# Register the root fixtures module so pytest discovers fixtures defined there.
# Only root-level (globally-scoped) fixtures go here. Subdirectory fixtures are
# re-exported from their local conftest.py to preserve directory scoping.
pytest_plugins = ["imbue.mng.fixtures"]
