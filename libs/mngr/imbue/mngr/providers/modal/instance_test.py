"""Tests for the ModalProviderInstance.

These tests require Modal credentials and network access to run. They are marked
with @pytest.mark.acceptance and are skipped by default. To run them:

    pytest -m modal --timeout=180

Or to run all tests including Modal tests:

    pytest --timeout=180
"""

import subprocess
from io import StringIO
from pathlib import Path
from typing import Any
from typing import Generator
from typing import cast
from unittest.mock import MagicMock
from unittest.mock import patch

import modal.exception
import pytest

from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.conftest import register_modal_test_app
from imbue.mngr.conftest import register_modal_test_environment
from imbue.mngr.conftest import register_modal_test_volume
from imbue.mngr.errors import HostNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ModalAuthError
from imbue.mngr.errors import SnapshotNotFoundError
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.primitives import SnapshotId
from imbue.mngr.primitives import SnapshotName
from imbue.mngr.providers.modal.backend import ModalProviderBackend
from imbue.mngr.providers.modal.backend import STATE_VOLUME_SUFFIX
from imbue.mngr.providers.modal.config import ModalProviderConfig
from imbue.mngr.providers.modal.constants import MODAL_TEST_APP_PREFIX
from imbue.mngr.providers.modal.instance import ModalProviderApp
from imbue.mngr.providers.modal.instance import ModalProviderInstance
from imbue.mngr.providers.modal.instance import TAG_HOST_ID
from imbue.mngr.providers.modal.instance import TAG_HOST_NAME
from imbue.mngr.providers.modal.instance import TAG_USER_PREFIX
from imbue.mngr.providers.modal.instance import _build_modal_secrets_from_env
from imbue.mngr.providers.modal.instance import build_sandbox_tags
from imbue.mngr.providers.modal.instance import parse_sandbox_tags

# =============================================================================
# Unit tests for sandbox tag helper functions
# =============================================================================


def test_build_sandbox_tags_with_no_user_tags() -> None:
    """build_sandbox_tags with no user tags should only include host_id and host_name."""
    host_id = HostId.generate()
    name = HostName("test-host")

    tags = build_sandbox_tags(host_id, name, None)

    assert tags == {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }


def test_build_sandbox_tags_with_empty_user_tags() -> None:
    """build_sandbox_tags with empty user tags dict should only include host_id and host_name."""
    host_id = HostId.generate()
    name = HostName("test-host")

    tags = build_sandbox_tags(host_id, name, {})

    assert tags == {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }


def test_build_sandbox_tags_with_user_tags() -> None:
    """build_sandbox_tags with user tags should prefix them with TAG_USER_PREFIX."""
    host_id = HostId.generate()
    name = HostName("test-host")
    user_tags = {"env": "production", "team": "backend"}

    tags = build_sandbox_tags(host_id, name, user_tags)

    assert tags[TAG_HOST_ID] == str(host_id)
    assert tags[TAG_HOST_NAME] == str(name)
    assert tags[TAG_USER_PREFIX + "env"] == "production"
    assert tags[TAG_USER_PREFIX + "team"] == "backend"
    assert len(tags) == 4


def test_parse_sandbox_tags_extracts_host_id_and_name() -> None:
    """parse_sandbox_tags should extract host_id and name from tags."""
    host_id = HostId.generate()
    name = HostName("test-host")
    tags = {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
    }

    parsed_host_id, parsed_name, parsed_user_tags = parse_sandbox_tags(tags)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_user_tags == {}


def test_parse_sandbox_tags_extracts_user_tags() -> None:
    """parse_sandbox_tags should extract user tags and strip the prefix."""
    host_id = HostId.generate()
    name = HostName("test-host")
    tags = {
        TAG_HOST_ID: str(host_id),
        TAG_HOST_NAME: str(name),
        TAG_USER_PREFIX + "env": "staging",
        TAG_USER_PREFIX + "version": "1.0.0",
    }

    parsed_host_id, parsed_name, parsed_user_tags = parse_sandbox_tags(tags)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_user_tags == {"env": "staging", "version": "1.0.0"}


def test_build_and_parse_sandbox_tags_roundtrip() -> None:
    """Building and parsing tags should round-trip correctly."""
    host_id = HostId.generate()
    name = HostName("my-test-host")
    user_tags = {"key1": "value1", "key2": "value2"}

    built_tags = build_sandbox_tags(host_id, name, user_tags)
    parsed_host_id, parsed_name, parsed_user_tags = parse_sandbox_tags(built_tags)

    assert parsed_host_id == host_id
    assert parsed_name == name
    assert parsed_user_tags == user_tags


def make_modal_provider_with_mocks(mngr_ctx: MngrContext, app_name: str) -> ModalProviderInstance:
    """Create a ModalProviderInstance with mocked Modal dependencies for unit tests.

    Uses model_construct() to bypass Pydantic validation, allowing MagicMock objects
    to be used in place of real modal.App and modal.Volume instances.
    """
    mock_app = MagicMock()
    mock_app.app_id = "mock-app-id"
    mock_app.name = app_name

    mock_volume = MagicMock()
    output_buffer = StringIO()

    # Create a mock environment name for testing
    mock_environment_name = f"test-env-{app_name}"

    # Create ModalProviderApp using model_construct to skip validation
    modal_app = ModalProviderApp.model_construct(
        app_name=app_name,
        environment_name=mock_environment_name,
        app=mock_app,
        volume=mock_volume,
        close_callback=MagicMock(),
        get_output_callback=output_buffer.getvalue,
    )

    # Create config for the provider instance
    # Set is_persistent=False for testing to enable cleanup
    config = ModalProviderConfig(
        app_name=app_name,
        host_dir=Path("/mngr"),
        default_timeout=300,
        default_cpu=0.5,
        default_memory=0.5,
        is_persistent=False,
    )

    # Create ModalProviderInstance using model_construct to skip validation
    instance = ModalProviderInstance.model_construct(
        name=ProviderInstanceName("modal-test"),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        config=config,
        modal_app=modal_app,
    )
    return instance


def make_modal_provider_real(
    mngr_ctx: MngrContext, app_name: str, is_persistent: bool = False
) -> ModalProviderInstance:
    """Create a ModalProviderInstance with real Modal for acceptance tests."""
    config = ModalProviderConfig(
        app_name=app_name,
        host_dir=Path("/mngr"),
        default_timeout=300,
        default_cpu=0.5,
        default_memory=0.5,
        is_persistent=is_persistent,
    )
    instance = ModalProviderBackend.build_provider_instance(
        name=ProviderInstanceName("modal-test"),
        config=config,
        mngr_ctx=mngr_ctx,
    )
    return cast(ModalProviderInstance, instance)


@pytest.fixture
def modal_provider(temp_mngr_ctx: MngrContext, mngr_test_id: str) -> ModalProviderInstance:
    """Create a ModalProviderInstance with mocked Modal for unit/integration tests."""
    app_name = f"{MODAL_TEST_APP_PREFIX}{mngr_test_id}"
    return make_modal_provider_with_mocks(temp_mngr_ctx, app_name)


def _cleanup_modal_test_resources(app_name: str, volume_name: str, environment_name: str) -> None:
    """Clean up Modal test resources after a test completes.

    This helper performs cleanup in the correct order:
    1. Close the Modal app context
    2. Delete the volume (must be done before environment deletion)
    3. Delete the environment (cleans up any remaining resources)
    """
    # Close the Modal app context first
    ModalProviderBackend.close_app(app_name)

    # Delete the volume (must be done before environment deletion)
    try:
        subprocess.run(
            ["uv", "run", "modal", "volume", "delete", volume_name, "--yes"],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass

    # Delete the environment (this also cleans up any remaining resources in it)
    try:
        subprocess.run(
            ["uv", "run", "modal", "environment", "delete", environment_name, "--yes"],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass


@pytest.fixture
def real_modal_provider(temp_mngr_ctx: MngrContext, mngr_test_id: str) -> Generator[ModalProviderInstance, None, None]:
    """Create a ModalProviderInstance with real Modal for acceptance tests.

    This fixture creates a Modal environment and cleans it up after the test.
    Cleanup happens in the fixture teardown (not at session end) to prevent
    environment leaks and reduce the time spent on cleanup.
    """
    app_name = f"{MODAL_TEST_APP_PREFIX}{mngr_test_id}"
    provider = make_modal_provider_real(temp_mngr_ctx, app_name)
    environment_name = provider.environment_name
    volume_name = f"{app_name}{STATE_VOLUME_SUFFIX}"

    # Register resources for leak detection (safety net in case cleanup fails)
    register_modal_test_app(app_name)
    register_modal_test_environment(environment_name)
    register_modal_test_volume(volume_name)

    yield provider

    _cleanup_modal_test_resources(app_name, volume_name, environment_name)


@pytest.fixture
def persistent_modal_provider(
    temp_mngr_ctx: MngrContext, mngr_test_id: str
) -> Generator[ModalProviderInstance, None, None]:
    """Create a persistent ModalProviderInstance for testing shutdown script creation.

    This fixture is similar to real_modal_provider but uses is_persistent=True,
    which enables the shutdown script feature.
    """
    app_name = f"{MODAL_TEST_APP_PREFIX}{mngr_test_id}"
    provider = make_modal_provider_real(temp_mngr_ctx, app_name, is_persistent=True)
    environment_name = provider.environment_name
    volume_name = f"{app_name}{STATE_VOLUME_SUFFIX}"

    # Register resources for leak detection
    register_modal_test_app(app_name)
    register_modal_test_environment(environment_name)
    register_modal_test_volume(volume_name)

    yield provider

    _cleanup_modal_test_resources(app_name, volume_name, environment_name)


# =============================================================================
# Basic property tests (no network required)
# =============================================================================


def test_modal_provider_name(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should have the correct name."""
    assert modal_provider.name == ProviderInstanceName("modal-test")


def test_modal_provider_supports_snapshots(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should support snapshots via sandbox.snapshot_filesystem()."""
    assert modal_provider.supports_snapshots is True


def test_modal_provider_does_not_support_volumes(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should not support volumes."""
    assert modal_provider.supports_volumes is False


def test_modal_provider_supports_mutable_tags(modal_provider: ModalProviderInstance) -> None:
    """Modal provider supports mutable tags via Modal's sandbox.set_tags() API."""
    assert modal_provider.supports_mutable_tags is True


def test_list_volumes_returns_empty_list(modal_provider: ModalProviderInstance) -> None:
    """Modal provider should return empty list for volumes."""
    volumes = modal_provider.list_volumes()
    assert volumes == []


def test_handle_modal_auth_error_decorator_converts_auth_error_to_modal_auth_error(
    modal_provider: ModalProviderInstance,
) -> None:
    """The @handle_modal_auth_error decorator should convert modal.exception.AuthError to ModalAuthError."""
    # Mock the _get_modal_app method to raise an AuthError
    with patch.object(modal_provider, "_get_modal_app") as mock_get_app:
        mock_get_app.side_effect = modal.exception.AuthError("Token missing")

        # list_hosts is decorated with @handle_modal_auth_error
        with pytest.raises(ModalAuthError) as exc_info:
            modal_provider.list_hosts()

        # Verify the error message contains helpful information
        error_message = str(exc_info.value)
        assert "Modal authentication failed" in error_message
        assert "--disable-plugin modal" in error_message
        assert "https://modal.com/docs/reference/modal.config" in error_message

        # Verify the original AuthError is chained
        assert isinstance(exc_info.value.__cause__, modal.exception.AuthError)


# =============================================================================
# Build args parsing tests (no network required)
# =============================================================================


def test_parse_build_args_empty(modal_provider: ModalProviderInstance) -> None:
    """Empty build args should return default config."""
    config = modal_provider._parse_build_args(None)
    assert config.gpu is None
    # These values come from the modal_provider fixture defaults
    assert config.cpu == 0.5
    assert config.memory == 0.5
    assert config.image is None
    assert config.timeout == 300

    config = modal_provider._parse_build_args([])
    assert config.gpu is None


def test_parse_build_args_key_value_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse simple key=value format."""
    config = modal_provider._parse_build_args(["gpu=h100", "cpu=2", "memory=8"])
    assert config.gpu == "h100"
    assert config.cpu == 2.0
    assert config.memory == 8.0


def test_parse_build_args_flag_equals_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse --key=value format."""
    config = modal_provider._parse_build_args(["--gpu=a100", "--cpu=4", "--memory=16"])
    assert config.gpu == "a100"
    assert config.cpu == 4.0
    assert config.memory == 16.0


def test_parse_build_args_flag_space_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse --key value format (two separate args)."""
    config = modal_provider._parse_build_args(["--gpu", "t4", "--cpu", "1", "--memory", "2"])
    assert config.gpu == "t4"
    assert config.cpu == 1.0
    assert config.memory == 2.0


def test_parse_build_args_mixed_formats(modal_provider: ModalProviderInstance) -> None:
    """Should parse mixed formats in same call."""
    config = modal_provider._parse_build_args(["gpu=h100", "--cpu=2", "--memory", "4"])
    assert config.gpu == "h100"
    assert config.cpu == 2.0
    assert config.memory == 4.0


def test_parse_build_args_image_and_timeout(modal_provider: ModalProviderInstance) -> None:
    """Should parse image and timeout arguments."""
    config = modal_provider._parse_build_args(["image=python:3.11-slim", "timeout=3600"])
    assert config.image == "python:3.11-slim"
    assert config.timeout == 3600


def test_parse_build_args_unknown_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Unknown build args should raise MngrError."""
    with pytest.raises(MngrError) as exc_info:
        modal_provider._parse_build_args(["gpu=h100", "unknown=value"])
    assert "Unknown build arguments" in str(exc_info.value)


def test_parse_build_args_invalid_type_raises_error(modal_provider: ModalProviderInstance) -> None:
    """Invalid type for numeric args should raise MngrError."""
    with pytest.raises(MngrError):
        modal_provider._parse_build_args(["cpu=not_a_number"])


def test_parse_build_args_value_with_equals(modal_provider: ModalProviderInstance) -> None:
    """Should handle values containing equals signs."""
    # Image names can contain = in tags
    config = modal_provider._parse_build_args(["--image=myregistry.com/image:tag=v1"])
    assert config.image == "myregistry.com/image:tag=v1"


def test_parse_build_args_region(modal_provider: ModalProviderInstance) -> None:
    """Should parse region argument."""
    config = modal_provider._parse_build_args(["region=us-east"])
    assert config.region == "us-east"

    config = modal_provider._parse_build_args(["--region=eu-west"])
    assert config.region == "eu-west"

    config = modal_provider._parse_build_args(["--region", "us-west"])
    assert config.region == "us-west"


def test_parse_build_args_region_default_is_none(modal_provider: ModalProviderInstance) -> None:
    """Region should default to None (auto-select)."""
    config = modal_provider._parse_build_args([])
    assert config.region is None

    config = modal_provider._parse_build_args(["cpu=2"])
    assert config.region is None


def test_parse_build_args_context_dir(modal_provider: ModalProviderInstance) -> None:
    """Should parse context-dir argument."""
    config = modal_provider._parse_build_args(["context-dir=/path/to/context"])
    assert config.context_dir == "/path/to/context"

    config = modal_provider._parse_build_args(["--context-dir=/another/path"])
    assert config.context_dir == "/another/path"

    config = modal_provider._parse_build_args(["--context-dir", "/third/path"])
    assert config.context_dir == "/third/path"


def test_parse_build_args_context_dir_default_is_none(modal_provider: ModalProviderInstance) -> None:
    """context_dir should default to None (use Dockerfile's directory)."""
    config = modal_provider._parse_build_args([])
    assert config.context_dir is None

    config = modal_provider._parse_build_args(["cpu=2"])
    assert config.context_dir is None


def test_parse_build_args_single_secret(modal_provider: ModalProviderInstance) -> None:
    """Should parse a single --secret argument."""
    config = modal_provider._parse_build_args(["--secret=MY_TOKEN"])
    assert config.secrets == ("MY_TOKEN",)


def test_parse_build_args_multiple_secrets(modal_provider: ModalProviderInstance) -> None:
    """Should parse multiple --secret arguments."""
    config = modal_provider._parse_build_args(["--secret=TOKEN1", "--secret=TOKEN2", "--secret=TOKEN3"])
    assert config.secrets == ("TOKEN1", "TOKEN2", "TOKEN3")


def test_parse_build_args_secret_with_key_value_format(modal_provider: ModalProviderInstance) -> None:
    """Should parse secret=VAR format."""
    config = modal_provider._parse_build_args(["secret=MY_TOKEN"])
    assert config.secrets == ("MY_TOKEN",)


def test_parse_build_args_secret_default_is_empty(modal_provider: ModalProviderInstance) -> None:
    """secrets should default to empty tuple."""
    config = modal_provider._parse_build_args([])
    assert config.secrets == ()

    config = modal_provider._parse_build_args(["cpu=2"])
    assert config.secrets == ()


def test_parse_build_args_secrets_with_other_args(modal_provider: ModalProviderInstance) -> None:
    """Should parse secrets alongside other build args."""
    config = modal_provider._parse_build_args(["cpu=2", "--secret=TOKEN1", "memory=4", "--secret=TOKEN2"])
    assert config.cpu == 2.0
    assert config.memory == 4.0
    assert config.secrets == ("TOKEN1", "TOKEN2")


# =============================================================================
# Tests for config-level defaults in _parse_build_args
# =============================================================================


def make_modal_provider_with_config_defaults(
    mngr_ctx: MngrContext,
    app_name: str,
    default_gpu: str | None = None,
    default_image: str | None = None,
    default_region: str | None = None,
) -> ModalProviderInstance:
    """Create a ModalProviderInstance with custom config defaults for testing."""
    mock_app = MagicMock()
    mock_app.app_id = "mock-app-id"
    mock_app.name = app_name

    mock_volume = MagicMock()
    output_buffer = StringIO()

    # Create a mock environment name for testing
    mock_environment_name = f"test-env-{app_name}"

    modal_app = ModalProviderApp.model_construct(
        app_name=app_name,
        environment_name=mock_environment_name,
        app=mock_app,
        volume=mock_volume,
        close_callback=MagicMock(),
        get_output_callback=output_buffer.getvalue,
    )

    config = ModalProviderConfig(
        app_name=app_name,
        host_dir=Path("/mngr"),
        default_timeout=300,
        default_cpu=0.5,
        default_memory=0.5,
        default_gpu=default_gpu,
        default_image=default_image,
        default_region=default_region,
        is_persistent=False,
    )

    instance = ModalProviderInstance.model_construct(
        name=ProviderInstanceName("modal-test"),
        host_dir=Path("/mngr"),
        mngr_ctx=mngr_ctx,
        config=config,
        modal_app=modal_app,
    )
    return instance


def test_parse_build_args_uses_config_default_gpu(temp_mngr_ctx: MngrContext) -> None:
    """When default_gpu is set in config, _parse_build_args should use it."""
    provider = make_modal_provider_with_config_defaults(
        temp_mngr_ctx,
        app_name="test-app",
        default_gpu="h100",
    )
    config = provider._parse_build_args([])
    assert config.gpu == "h100"

    # Empty list should also use default
    config = provider._parse_build_args(None)
    assert config.gpu == "h100"


def test_parse_build_args_uses_config_default_image(temp_mngr_ctx: MngrContext) -> None:
    """When default_image is set in config, _parse_build_args should use it."""
    provider = make_modal_provider_with_config_defaults(
        temp_mngr_ctx,
        app_name="test-app",
        default_image="python:3.11-slim",
    )
    config = provider._parse_build_args([])
    assert config.image == "python:3.11-slim"


def test_parse_build_args_uses_config_default_region(temp_mngr_ctx: MngrContext) -> None:
    """When default_region is set in config, _parse_build_args should use it."""
    provider = make_modal_provider_with_config_defaults(
        temp_mngr_ctx,
        app_name="test-app",
        default_region="us-east",
    )
    config = provider._parse_build_args([])
    assert config.region == "us-east"


def test_parse_build_args_uses_all_config_defaults(temp_mngr_ctx: MngrContext) -> None:
    """When all defaults are set in config, _parse_build_args should use them."""
    provider = make_modal_provider_with_config_defaults(
        temp_mngr_ctx,
        app_name="test-app",
        default_gpu="a100",
        default_image="ubuntu:22.04",
        default_region="eu-west",
    )
    config = provider._parse_build_args([])
    assert config.gpu == "a100"
    assert config.image == "ubuntu:22.04"
    assert config.region == "eu-west"


def test_parse_build_args_explicit_args_override_config_defaults(temp_mngr_ctx: MngrContext) -> None:
    """Explicit build args should override config defaults."""
    provider = make_modal_provider_with_config_defaults(
        temp_mngr_ctx,
        app_name="test-app",
        default_gpu="h100",
        default_image="python:3.11-slim",
        default_region="us-east",
    )

    # Override GPU
    config = provider._parse_build_args(["--gpu=a100"])
    assert config.gpu == "a100"
    assert config.image == "python:3.11-slim"
    assert config.region == "us-east"

    # Override image
    config = provider._parse_build_args(["--image=debian:bookworm"])
    assert config.gpu == "h100"
    assert config.image == "debian:bookworm"
    assert config.region == "us-east"

    # Override region
    config = provider._parse_build_args(["--region=eu-west"])
    assert config.gpu == "h100"
    assert config.image == "python:3.11-slim"
    assert config.region == "eu-west"

    # Override all
    config = provider._parse_build_args(["--gpu=t4", "--image=alpine:latest", "--region=ap-south"])
    assert config.gpu == "t4"
    assert config.image == "alpine:latest"
    assert config.region == "ap-south"


# =============================================================================
# Tests for _build_modal_secrets_from_env helper function
# =============================================================================


def test_build_modal_secrets_from_env_empty_list() -> None:
    """Empty list of env vars should return empty list of secrets."""
    result = _build_modal_secrets_from_env([])
    assert result == []


def test_build_modal_secrets_from_env_with_set_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should create secrets from environment variables that are set."""
    monkeypatch.setenv("TEST_SECRET_1", "value1")
    monkeypatch.setenv("TEST_SECRET_2", "value2")

    result = _build_modal_secrets_from_env(["TEST_SECRET_1", "TEST_SECRET_2"])

    # All vars are combined into one Secret
    assert len(result) == 1


def test_build_modal_secrets_from_env_missing_var_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should raise MngrError when an environment variable is not set."""
    # Ensure the variable is not set
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)

    with pytest.raises(MngrError) as exc_info:
        _build_modal_secrets_from_env(["NONEXISTENT_VAR"])

    assert "Environment variable(s) not set for secrets" in str(exc_info.value)
    assert "NONEXISTENT_VAR" in str(exc_info.value)


def test_build_modal_secrets_from_env_multiple_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should report all missing environment variables in the error."""
    monkeypatch.delenv("MISSING_VAR_1", raising=False)
    monkeypatch.delenv("MISSING_VAR_2", raising=False)

    with pytest.raises(MngrError) as exc_info:
        _build_modal_secrets_from_env(["MISSING_VAR_1", "MISSING_VAR_2"])

    error_message = str(exc_info.value)
    assert "MISSING_VAR_1" in error_message
    assert "MISSING_VAR_2" in error_message


def test_build_modal_secrets_from_env_partial_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should raise error listing only the missing vars when some are set."""
    monkeypatch.setenv("SET_VAR", "value")
    monkeypatch.delenv("MISSING_VAR", raising=False)

    with pytest.raises(MngrError) as exc_info:
        _build_modal_secrets_from_env(["SET_VAR", "MISSING_VAR"])

    error_message = str(exc_info.value)
    assert "MISSING_VAR" in error_message
    assert "SET_VAR" not in error_message


# =============================================================================
# Tests for _create_shutdown_script helper method
# =============================================================================


def test_create_shutdown_script_generates_correct_content(
    modal_provider: ModalProviderInstance,
) -> None:
    """_create_shutdown_script should generate a script with correct content."""
    # Create a simple mock host that captures the written content
    written_content: dict[str, str] = {}
    written_modes: dict[str, str] = {}

    class MockHost:
        host_dir = Path("/mngr")

        def write_text_file(self, path: Path, content: str, mode: str | None = None) -> None:
            written_content[str(path)] = content
            if mode:
                written_modes[str(path)] = mode

    mock_host = MockHost()

    # Create a mock sandbox with an object_id
    mock_sandbox = MagicMock()
    mock_sandbox.object_id = "sb-test-sandbox-123"

    # Call the method with a test URL
    host_id = HostId.generate()
    snapshot_url = "https://test--app-snapshot-and-shutdown.modal.run"

    modal_provider._create_shutdown_script(
        cast(Any, mock_host),
        mock_sandbox,
        host_id,
        snapshot_url,
    )

    # Verify the script was written to the correct path
    expected_path = "/mngr/commands/shutdown.sh"
    assert expected_path in written_content

    # Verify the script content
    script = written_content[expected_path]
    assert "#!/bin/bash" in script
    assert snapshot_url in script
    assert "sb-test-sandbox-123" in script
    assert str(host_id) in script
    assert "curl" in script
    assert "Content-Type: application/json" in script

    # Verify the mode is executable
    assert written_modes[expected_path] == "755"


# =============================================================================
# Acceptance tests (require Modal network access)
# =============================================================================


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_create_host_creates_sandbox_with_ssh(real_modal_provider: ModalProviderInstance) -> None:
    """Creating a host should create a Modal sandbox with SSH access."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))

        # Verify host was created
        assert host.id is not None
        assert host.connector is not None

        # Verify SSH connector type
        assert host.connector.connector_cls_name == "SSHConnector"

        # Verify we can execute commands via SSH
        result = host.execute_command("echo 'hello from modal'")
        assert result.success
        assert "hello from modal" in result.stdout

        # Verify output capture is working (Modal should emit some output during host creation)
        captured_output = real_modal_provider.get_captured_output()
        assert isinstance(captured_output, str)

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_persistent_host_creates_shutdown_script(
    persistent_modal_provider: ModalProviderInstance,
) -> None:
    """Persistent Modal host should have a shutdown script created.

    This test verifies that when using a persistent Modal app (is_persistent=True),
    the snapshot_and_shutdown function is deployed and a shutdown script is written
    to the host at <host_dir>/commands/shutdown.sh.
    """
    host = None
    try:
        host = persistent_modal_provider.create_host(HostName("test-host"))

        # Verify host was created
        assert host.id is not None

        # Check that the shutdown script exists on the host
        result = host.execute_command("test -f /mngr/commands/shutdown.sh && echo 'exists'")
        assert result.success
        assert "exists" in result.stdout

        # Verify the script content contains expected values
        result = host.execute_command("cat /mngr/commands/shutdown.sh")
        assert result.success
        script_content = result.stdout

        # Check script has expected structure
        assert "#!/bin/bash" in script_content
        assert "curl" in script_content
        assert "snapshot_and_shutdown" in script_content or "modal.run" in script_content
        assert str(host.id) in script_content

        # Verify the script is executable
        result = host.execute_command("test -x /mngr/commands/shutdown.sh && echo 'executable'")
        assert result.success
        assert "executable" in result.stdout

    finally:
        if host:
            persistent_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_get_host_by_id(real_modal_provider: ModalProviderInstance) -> None:
    """Should be able to get a host by its ID."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Get the same host by ID
        retrieved_host = real_modal_provider.get_host(host_id)
        assert retrieved_host.id == host_id

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_get_host_by_name(real_modal_provider: ModalProviderInstance) -> None:
    """Should be able to get a host by its name."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Get the same host by name
        retrieved_host = real_modal_provider.get_host(HostName("test-host"))
        assert retrieved_host.id == host_id

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_list_hosts_includes_created_host(real_modal_provider: ModalProviderInstance) -> None:
    """Created host should appear in list_hosts."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))

        hosts = real_modal_provider.list_hosts()
        host_ids = [h.id for h in hosts]
        assert host.id in host_ids

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_destroy_host_removes_sandbox(real_modal_provider: ModalProviderInstance) -> None:
    """Destroying a host should remove it from the provider."""
    host = real_modal_provider.create_host(HostName("test-host"))
    host_id = host.id

    real_modal_provider.destroy_host(host)

    # Host should no longer be found
    with pytest.raises(HostNotFoundError):
        real_modal_provider.get_host(host_id)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_get_host_resources(real_modal_provider: ModalProviderInstance) -> None:
    """Should be able to get resource information for a host."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))
        resources = real_modal_provider.get_host_resources(host)

        assert resources.cpu.count >= 1
        assert resources.memory_gb >= 0.5

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_get_and_set_host_tags(real_modal_provider: ModalProviderInstance) -> None:
    """Should be able to get and set tags on a host."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))

        # Initially no tags
        tags = real_modal_provider.get_host_tags(host)
        assert tags == {}

        # Set some tags
        real_modal_provider.set_host_tags(host, {"env": "test", "team": "backend"})
        tags = real_modal_provider.get_host_tags(host)
        assert tags == {"env": "test", "team": "backend"}

        # Add a tag
        real_modal_provider.add_tags_to_host(host, {"version": "1.0"})
        tags = real_modal_provider.get_host_tags(host)
        assert len(tags) == 3
        assert tags["version"] == "1.0"

        # Remove a tag
        real_modal_provider.remove_tags_from_host(host, ["team"])
        tags = real_modal_provider.get_host_tags(host)
        assert "team" not in tags
        assert len(tags) == 2

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_create_and_list_snapshots(real_modal_provider: ModalProviderInstance) -> None:
    """Should be able to create and list snapshots."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))

        # Initially there is one snapshot (the initial snapshot created during host creation)
        snapshots = real_modal_provider.list_snapshots(host)
        assert len(snapshots) == 1
        assert snapshots[0].name == "initial"

        # Create a snapshot
        snapshot_id = real_modal_provider.create_snapshot(host, SnapshotName("test-snapshot"))
        assert snapshot_id is not None

        # Verify it appears in the list (now 2 snapshots)
        snapshots = real_modal_provider.list_snapshots(host)
        assert len(snapshots) == 2
        # Most recent snapshot is first (recency_idx == 0)
        assert snapshots[0].id == snapshot_id
        assert snapshots[0].name == SnapshotName("test-snapshot")
        assert snapshots[0].recency_idx == 0
        # Initial snapshot is second
        assert snapshots[1].name == "initial"
        assert snapshots[1].recency_idx == 1

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_list_snapshots_returns_initial_snapshot(real_modal_provider: ModalProviderInstance) -> None:
    """list_snapshots should return the initial snapshot for a new host."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))
        snapshots = real_modal_provider.list_snapshots(host)
        assert len(snapshots) == 1
        assert snapshots[0].name == "initial"

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_delete_snapshot(real_modal_provider: ModalProviderInstance) -> None:
    """Should be able to delete a snapshot."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))

        # Initially there's 1 snapshot (the initial snapshot)
        assert len(real_modal_provider.list_snapshots(host)) == 1

        # Create a snapshot
        snapshot_id = real_modal_provider.create_snapshot(host)
        assert len(real_modal_provider.list_snapshots(host)) == 2

        # Delete the created snapshot
        real_modal_provider.delete_snapshot(host, snapshot_id)
        # Should be back to just the initial snapshot
        assert len(real_modal_provider.list_snapshots(host)) == 1

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_delete_nonexistent_snapshot_raises_error(real_modal_provider: ModalProviderInstance) -> None:
    """Deleting a nonexistent snapshot should raise SnapshotNotFoundError."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))

        fake_id = SnapshotId.generate()
        with pytest.raises(SnapshotNotFoundError):
            real_modal_provider.delete_snapshot(host, fake_id)

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_start_host_restores_from_snapshot(real_modal_provider: ModalProviderInstance) -> None:
    """start_host with a snapshot_id should restore a terminated host from the snapshot."""
    host = None
    restored_host = None
    try:
        # Create a host and write a marker file
        host = real_modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Write a marker file to verify restoration
        result = host.execute_command("echo 'snapshot-marker' > /tmp/marker.txt")
        assert result.success

        # Create a snapshot
        snapshot_id = real_modal_provider.create_snapshot(host, SnapshotName("test-restore"))

        # Verify snapshot exists (2 total: initial + test-restore)
        snapshots = real_modal_provider.list_snapshots(host)
        assert len(snapshots) == 2
        # Most recent is first
        assert snapshots[0].id == snapshot_id

        # Stop the host (terminates the sandbox)
        real_modal_provider.stop_host(host)

        # Restore from snapshot
        restored_host = real_modal_provider.start_host(host_id, snapshot_id=snapshot_id)

        # Verify the host was restored with the same ID
        assert restored_host.id == host_id

        # Verify the marker file exists (proving we restored from snapshot)
        result = restored_host.execute_command("cat /tmp/marker.txt")
        assert result.success
        assert "snapshot-marker" in result.stdout

    finally:
        if restored_host:
            real_modal_provider.destroy_host(restored_host)
        elif host:
            real_modal_provider.destroy_host(host)
        else:
            pass


@pytest.mark.acceptance
@pytest.mark.timeout(180)
def test_start_host_on_running_host(real_modal_provider: ModalProviderInstance) -> None:
    """start_host on a running host should return the same host."""
    host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Starting a running host should just return it
        started_host = real_modal_provider.start_host(host)
        assert started_host.id == host_id

    finally:
        if host:
            real_modal_provider.destroy_host(host)


@pytest.mark.acceptance
@pytest.mark.timeout(300)
def test_start_host_on_stopped_host_uses_initial_snapshot(real_modal_provider: ModalProviderInstance) -> None:
    """start_host on a terminated host should restart from the initial snapshot."""
    host = None
    restarted_host = None
    try:
        host = real_modal_provider.create_host(HostName("test-host"))
        host_id = host.id

        # Verify an initial snapshot was created
        snapshots = real_modal_provider.list_snapshots(host)
        assert len(snapshots) == 1
        assert snapshots[0].name == "initial"

        # Stop the host
        real_modal_provider.stop_host(host)

        # Start it again without specifying a snapshot - should use the initial snapshot
        restarted_host = real_modal_provider.start_host(host_id)

        # Verify the host was restarted with the same ID
        assert restarted_host.id == host_id

        # Verify we can execute commands on the restarted host
        result = restarted_host.execute_command("echo 'restarted successfully'")
        assert result.success
        assert "restarted successfully" in result.stdout

    finally:
        if restarted_host:
            real_modal_provider.destroy_host(restarted_host)
        elif host:
            real_modal_provider.destroy_host(host)
        else:
            pass


@pytest.mark.acceptance
def test_get_host_not_found_raises_error(real_modal_provider: ModalProviderInstance) -> None:
    """Getting a non-existent host should raise HostNotFoundError."""
    fake_id = HostId.generate()
    with pytest.raises(HostNotFoundError):
        real_modal_provider.get_host(fake_id)


@pytest.mark.acceptance
def test_get_host_by_name_not_found_raises_error(real_modal_provider: ModalProviderInstance) -> None:
    """Getting a non-existent host by name should raise HostNotFoundError."""
    with pytest.raises(HostNotFoundError):
        real_modal_provider.get_host(HostName("nonexistent-host"))
