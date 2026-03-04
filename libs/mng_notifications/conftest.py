"""Project-level conftest for mng-notifications.

When running tests from libs/mng_notifications/, this conftest provides the common pytest hooks
that would otherwise come from the monorepo root conftest.py (which is not discovered
when pytest runs from a subdirectory).

When running from the monorepo root, the root conftest.py registers the hooks first,
and this file's register_conftest_hooks() call is a no-op (guarded by a module-level flag).
"""

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.imbue_common.conftest_hooks import register_marker
from imbue.imbue_common.resource_guards import register_resource_guard
from imbue.mng.utils.logging import suppress_warnings

suppress_warnings()

register_marker("tmux: marks tests that start real tmux sessions")
register_resource_guard("tmux")

register_conftest_hooks(globals())
