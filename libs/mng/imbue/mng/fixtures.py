from pathlib import Path
from typing import Generator
from uuid import uuid4

import pluggy
import pytest
from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.config.data_types import PROFILES_DIRNAME
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.primitives import UserId
from imbue.mng.providers.local.instance import LocalProviderInstance
from imbue.mng.utils.testing import delete_modal_apps_in_environment
from imbue.mng.utils.testing import delete_modal_environment
from imbue.mng.utils.testing import delete_modal_volumes_in_environment
from imbue.mng.utils.testing import generate_test_environment_name
from imbue.mng.utils.testing import get_subprocess_test_env
from imbue.mng.utils.testing import init_git_repo

# Track test IDs used by this worker/process for cleanup verification.
# Each xdist worker is a separate process with isolated memory, so this
# list only contains IDs from tests run by THIS worker.
worker_test_ids: list[str] = []

# Track Modal app names that were created during tests for cleanup verification.
# This enables detection of leaked apps that weren't properly cleaned up.
worker_modal_app_names: list[str] = []

# Track Modal volume names that were created during tests for cleanup verification.
# Unlike Modal Apps, volumes are global to the account (not app-specific), so they
# must be tracked and cleaned up separately.
worker_modal_volume_names: list[str] = []

# Track Modal environment names that were created during tests for cleanup verification.
# Modal environments are used to scope all resources (apps, volumes, sandboxes) to a
# specific user.
worker_modal_environment_names: list[str] = []


def register_modal_test_app(app_name: str) -> None:
    """Register a Modal app name for cleanup verification.

    Call this when creating a Modal app during tests to enable leak detection.
    The app_name should match the name used when creating the Modal app.
    """
    if app_name not in worker_modal_app_names:
        worker_modal_app_names.append(app_name)


def register_modal_test_volume(volume_name: str) -> None:
    """Register a Modal volume name for cleanup verification.

    Call this when creating a Modal volume during tests to enable leak detection.
    The volume_name should match the name used when creating the Modal volume.
    """
    if volume_name not in worker_modal_volume_names:
        worker_modal_volume_names.append(volume_name)


def register_modal_test_environment(environment_name: str) -> None:
    """Register a Modal environment name for cleanup verification.

    Call this when creating a Modal environment during tests to enable leak detection.
    The environment_name should match the name used when creating resources in that environment.
    """
    if environment_name not in worker_modal_environment_names:
        worker_modal_environment_names.append(environment_name)


@pytest.fixture
def cg() -> Generator[ConcurrencyGroup, None, None]:
    """Provide a ConcurrencyGroup for tests that need to run processes."""
    with ConcurrencyGroup(name="test") as group:
        yield group


@pytest.fixture
def mng_test_id() -> str:
    """Generate a unique test ID for isolation.

    This ID is used for both the host directory and prefix to ensure
    test isolation and easy cleanup of test resources (e.g., tmux sessions).
    """
    test_id = uuid4().hex
    worker_test_ids.append(test_id)
    return test_id


@pytest.fixture
def mng_test_prefix(mng_test_id: str) -> str:
    """Get the test prefix for tmux session names.

    Format: mng_{test_id}- (underscore separator for easy cleanup).
    """
    return f"mng_{mng_test_id}-"


@pytest.fixture
def mng_test_root_name(mng_test_id: str) -> str:
    """Get the test root name for config isolation.

    Format: mng-test-{test_id}

    This ensures tests don't load the project's .mng/settings.toml config,
    which might have settings like add_command that would interfere with tests.
    """
    return f"mng-test-{mng_test_id}"


@pytest.fixture
def temp_host_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for host/mng data.

    This fixture creates .mng inside tmp_path (which becomes the fake HOME),
    ensuring tests don't write to the real ~/.mng.
    """
    host_dir = tmp_path / ".mng"
    host_dir.mkdir()
    return host_dir


@pytest.fixture
def tmp_home_dir(tmp_path: Path) -> Generator[Path, None, None]:
    yield tmp_path


@pytest.fixture
def setup_git_config(tmp_path: Path) -> None:
    """Create a .gitconfig in the fake HOME so git commands work.

    Use this fixture for any test that runs git commands.
    The temp_git_repo fixture depends on this, so you don't need both.
    """
    gitconfig = tmp_path / ".gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text("[user]\n\tname = Test User\n\temail = test@test.com\n")


@pytest.fixture
def temp_git_repo(tmp_path: Path, setup_git_config: None) -> Path:
    """Create a temporary git repository with an initial commit.

    This fixture:
    1. Ensures .gitconfig exists in the fake HOME (via setup_git_config)
    2. Creates a git repo with one tracked file and an initial commit

    Use this fixture for any test that needs a git repository.
    """
    repo_dir = tmp_path / "git_repo"
    repo_dir.mkdir()

    init_git_repo(repo_dir)

    return repo_dir


@pytest.fixture
def temp_work_dir(tmp_path: Path) -> Path:
    """Create a temporary work_dir directory for agents."""
    work_dir = tmp_path / "work_dir"
    work_dir.mkdir()
    return work_dir


@pytest.fixture
def temp_profile_dir(temp_host_dir: Path) -> Path:
    """Create a temporary profile directory.

    Use this fixture when tests need to create their own MngContext with custom config.
    """
    profile_dir = temp_host_dir / PROFILES_DIRNAME / uuid4().hex
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


@pytest.fixture
def temp_config(temp_host_dir: Path, mng_test_prefix: str) -> MngConfig:
    """Create a MngConfig with a temporary host directory.

    Use this fixture when calling API functions that need a config.
    """
    return MngConfig(default_host_dir=temp_host_dir, prefix=mng_test_prefix, is_error_reporting_enabled=False)


def make_mng_ctx(
    config: MngConfig,
    pm: pluggy.PluginManager,
    profile_dir: Path,
    *,
    is_interactive: bool = False,
    is_auto_approve: bool = False,
    concurrency_group: ConcurrencyGroup,
) -> MngContext:
    """Create a MngContext with the given parameters.

    Use this directly in tests that need non-default settings (e.g., interactive mode).
    Most tests should use the temp_mng_ctx fixture instead.
    """
    return MngContext(
        config=config,
        pm=pm,
        profile_dir=profile_dir,
        is_interactive=is_interactive,
        is_auto_approve=is_auto_approve,
        concurrency_group=concurrency_group,
    )


@pytest.fixture
def temp_mng_ctx(
    temp_config: MngConfig, temp_profile_dir: Path, plugin_manager: pluggy.PluginManager
) -> Generator[MngContext, None, None]:
    """Create a MngContext with a temporary host directory.

    Use this fixture when calling API functions that need a context.
    """
    cg = ConcurrencyGroup(name="test")
    with cg:
        yield make_mng_ctx(temp_config, plugin_manager, temp_profile_dir, concurrency_group=cg)


@pytest.fixture
def local_provider(temp_host_dir: Path, temp_mng_ctx: MngContext) -> LocalProviderInstance:
    """Create a LocalProviderInstance with a temporary host directory."""
    return LocalProviderInstance(
        name=ProviderInstanceName("local"),
        host_dir=temp_host_dir,
        mng_ctx=temp_mng_ctx,
    )


@pytest.fixture
def per_host_dir(temp_host_dir: Path) -> Path:
    """Get the host directory for the local provider.

    This is the directory where host-scoped data lives: agents/, data.json,
    activity/, etc. This is the same as temp_host_dir (e.g. ~/.mng/).
    """
    return temp_host_dir


# =============================================================================
# Modal subprocess test environment fixture (session-scoped)
# =============================================================================


class ModalSubprocessTestEnv(FrozenModel):
    """Environment configuration for Modal subprocess tests."""

    env: dict[str, str] = Field(description="Environment variables for the subprocess")
    prefix: str = Field(description="The mng prefix for test isolation")
    host_dir: Path = Field(description="Path to the temporary host directory")


@pytest.fixture(scope="session")
def modal_test_session_env_name() -> str:
    """Generate a unique, timestamp-based environment name for this test session.

    This fixture is session-scoped, so all tests in a session share the same
    environment name. The name includes a UTC timestamp in the format:
    mng_test-YYYY-MM-DD-HH-MM-SS
    """
    return generate_test_environment_name()


@pytest.fixture(scope="session")
def modal_test_session_host_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a session-scoped host directory for Modal tests.

    This ensures all tests in a session share the same host directory,
    which means they share the same Modal environment.
    """
    host_dir = tmp_path_factory.mktemp("modal_session") / "mng"
    host_dir.mkdir(parents=True, exist_ok=True)
    return host_dir


@pytest.fixture(scope="session")
def modal_test_session_user_id() -> UserId:
    """Generate a deterministic user ID for the test session.

    This user ID is shared across all subprocess Modal tests in a session
    via the MNG_USER_ID environment variable. By generating it upfront,
    the cleanup fixture can construct the exact environment name without
    needing to find the user_id file in the profile directory structure.
    """
    return UserId(uuid4().hex)


@pytest.fixture(scope="session")
def modal_test_session_cleanup(
    modal_test_session_env_name: str,
    modal_test_session_user_id: UserId,
) -> Generator[None, None, None]:
    """Session-scoped fixture that cleans up the Modal environment at session end.

    This fixture ensures the Modal environment created for tests is deleted
    when the test session completes, including all apps and volumes.
    """
    yield

    # Clean up Modal environment after the session.
    # The environment name is {prefix}{user_id}, where prefix is based on the timestamp
    # and user_id is the session-scoped deterministic ID.
    prefix = f"{modal_test_session_env_name}-"
    environment_name = f"{prefix}{modal_test_session_user_id}"

    # Truncate environment_name if needed (Modal has 64 char limit)
    if len(environment_name) > 64:
        environment_name = environment_name[:64]

    # Delete apps, volumes, and environment using functions from testing.py
    delete_modal_apps_in_environment(environment_name)
    delete_modal_volumes_in_environment(environment_name)
    delete_modal_environment(environment_name)


@pytest.fixture
def modal_subprocess_env(
    modal_test_session_env_name: str,
    modal_test_session_host_dir: Path,
    modal_test_session_cleanup: None,
    modal_test_session_user_id: UserId,
) -> Generator[ModalSubprocessTestEnv, None, None]:
    """Create a subprocess test environment with session-scoped Modal environment.

    This fixture:
    1. Uses a session-scoped MNG_PREFIX based on UTC timestamp (mng_test-YYYY-MM-DD-HH-MM-SS)
    2. Uses a session-scoped MNG_HOST_DIR so all tests share the same host directory
    3. Sets MNG_USER_ID so all subprocesses use the same deterministic user ID
    4. Cleans up the Modal environment at the end of the session (not per-test)

    Using session-scoped environments reduces the number of environments created
    and makes cleanup easier (environments have timestamps in their names).
    """
    prefix = f"{modal_test_session_env_name}-"
    host_dir = modal_test_session_host_dir

    env = get_subprocess_test_env(
        root_name="mng-acceptance-test",
        prefix=prefix,
        host_dir=host_dir,
    )
    # Set the user ID so all subprocesses use the same deterministic ID.
    # This ensures the cleanup fixture can construct the exact environment name.
    env["MNG_USER_ID"] = modal_test_session_user_id

    yield ModalSubprocessTestEnv(env=env, prefix=prefix, host_dir=host_dir)
