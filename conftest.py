"""Root conftest for the monorepo.

Common pytest hooks (test locking, timing limits, output file redirection) are
provided by the shared module imbue.imbue_common.conftest_hooks. Each project's
conftest.py calls register_conftest_hooks(globals()) to inject them. The shared
module ensures hooks are only registered once even when multiple conftest.py files
are discovered (e.g., when running from the monorepo root).
"""

from imbue.imbue_common.conftest_hooks import register_conftest_hooks
from imbue.imbue_common.resource_guards import register_resource_guard
from imbue.mng.utils.logging import suppress_warnings

# Suppress some pointless warnings from other library's loggers
suppress_warnings()

# Register guarded resources (CLI binaries that require corresponding pytest marks).
# Docker and Modal use Python SDKs (not CLI binaries), so they are not guarded here.
for _resource in ("tmux", "rsync", "unison"):
    register_resource_guard(_resource)

# Register the common conftest hooks (locking, timing, output file redirection)
register_conftest_hooks(globals())
