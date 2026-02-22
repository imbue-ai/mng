"""Project-level conftest for mng.

When running tests from libs/mng/, this conftest provides the common pytest hooks
that would otherwise come from the monorepo root conftest.py (which is not discovered
when pytest runs from a subdirectory).

When running from the monorepo root, the root conftest.py registers the hooks first,
and this file's register_conftest_hooks() call is a no-op (guarded by a module-level flag).
"""

from imbue.imbue_common.conftest_hooks import register_conftest_hooks

# re-export fixtures here so pytest discovers them scoped to this directory.
# we keep fixture definitions in fixtures.py so agents can glob for them.
from imbue.mng.fixtures import cg as cg
from imbue.mng.fixtures import local_provider as local_provider
from imbue.mng.fixtures import mng_test_id as mng_test_id
from imbue.mng.fixtures import mng_test_prefix as mng_test_prefix
from imbue.mng.fixtures import mng_test_root_name as mng_test_root_name
from imbue.mng.fixtures import modal_subprocess_env as modal_subprocess_env
from imbue.mng.fixtures import modal_test_session_cleanup as modal_test_session_cleanup
from imbue.mng.fixtures import modal_test_session_env_name as modal_test_session_env_name
from imbue.mng.fixtures import modal_test_session_host_dir as modal_test_session_host_dir
from imbue.mng.fixtures import modal_test_session_user_id as modal_test_session_user_id
from imbue.mng.fixtures import per_host_dir as per_host_dir
from imbue.mng.fixtures import setup_git_config as setup_git_config
from imbue.mng.fixtures import temp_config as temp_config
from imbue.mng.fixtures import temp_git_repo as temp_git_repo
from imbue.mng.fixtures import temp_host_dir as temp_host_dir
from imbue.mng.fixtures import temp_mng_ctx as temp_mng_ctx
from imbue.mng.fixtures import temp_profile_dir as temp_profile_dir
from imbue.mng.fixtures import temp_work_dir as temp_work_dir
from imbue.mng.fixtures import tmp_home_dir as tmp_home_dir
from imbue.mng.utils.logging import suppress_warnings

suppress_warnings()
register_conftest_hooks(globals())
