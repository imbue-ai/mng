import contextlib
import json
import subprocess
from pathlib import Path
from typing import Any
from typing import ClassVar
from uuid import uuid4

import modal
import modal.exception
from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import ProviderInstanceConfig
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.modal.config import ModalProviderConfig
from imbue.mngr.providers.modal.instance import ModalProviderApp
from imbue.mngr.providers.modal.instance import ModalProviderInstance
from imbue.mngr.providers.modal.log_utils import enable_modal_output_capture

MODAL_BACKEND_NAME = ProviderBackendName("modal")
USER_ID_FILENAME = "user_id"
STATE_VOLUME_SUFFIX = "-state"
MODAL_NAME_MAX_LENGTH = 64


# FIXME: this should just be renamed to _create_environment, and we should delete the first check, since it is only called when the env is missing
def _ensure_environment_exists(environment_name: str) -> None:
    """Ensure a Modal environment exists, creating it if necessary.

    Modal environments must be created before they can be used to scope resources
    like apps, volumes, and sandboxes. Since the Modal Python SDK doesn't provide
    an API for managing environments, we use the CLI.
    """
    # Check if the environment exists by listing environments
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            environments = json.loads(result.stdout)
            for env in environments:
                if env.get("name") == environment_name:
                    logger.trace("Modal environment already exists: {}", environment_name)
                    return
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        # If we can't list environments, try to create anyway
        pass

    # Environment doesn't exist, create it
    logger.debug("Creating Modal environment: {}", environment_name)
    try:
        result = subprocess.run(
            ["uv", "run", "modal", "environment", "create", environment_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Created Modal environment: {}", environment_name)
        else:
            # If creation fails, it might already exist (race condition) or there's an error
            # We'll let the subsequent Modal API calls fail with a more specific error if needed
            logger.debug("Modal environment create returned non-zero: {}", result.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.warning("Failed to create Modal environment via CLI: {}", e)


class ModalAppContextHandle(FrozenModel):
    """Handle for managing a Modal app context lifecycle with output capture.

    This class captures a Modal app's run context along with the output capture
    context. The output buffer can be inspected to detect build failures and
    other issues in the Modal logs.

    Also manages the state volume for persisting host records across sandbox
    termination. The volume is created lazily when first accessed.
    """

    # FIXME: replace Any with concrete types from modal
    #  you'll need a config dict like this:
    #      model_config = ConfigDict(arbitrary_types_allowed=True)
    run_context: Any | None = Field(
        description="The Modal app.run() context manager (only present for ephemeral apps)"
    )
    app_name: str = Field(description="The name of the Modal app")
    environment_name: str = Field(description="The Modal environment name for user isolation")
    output_capture_context: Any = Field(description="The output capture context manager")
    output_buffer: Any = Field(description="StringIO buffer containing captured Modal output")
    loguru_writer: Any = Field(description="Loguru writer for structured logging (or None)")
    volume_name: str = Field(description="Name of the state volume for persisting host records")
    volume: Any = Field(default=None, description="The Modal volume for state storage (lazily created)")


def _exit_modal_app_context(handle: ModalAppContextHandle) -> None:
    """Exit a Modal app context and its output capture context."""
    logger.debug("Exiting Modal app context: {}", handle.app_name)

    # Log any captured output for debugging
    captured_output = handle.output_buffer.getvalue()
    if captured_output:
        logger.trace("Modal output captured ({} chars): {}", len(captured_output), captured_output[:500])

    # Exit the app context first
    try:
        if handle.run_context is not None:
            handle.run_context.__exit__(None, None, None)
    except modal.exception.Error as e:
        logger.warning("Modal error exiting app context {}: {}", handle.app_name, e)

    # Exit the output capture context - this is a cleanup operation so we just
    # suppress any errors
    with contextlib.suppress(OSError, RuntimeError):
        handle.output_capture_context.__exit__(None, None, None)


# FIXME: this function should be moved to a much lower level (many other things may want a user id, should be part of MngrContext?)
#  also, obviously this should return a concrete type, not a str
def _get_or_create_user_id(mngr_ctx: MngrContext) -> str:
    """Get or create a unique user ID for this mngr installation.

    The user ID is stored in a file in the mngr data directory. This ID is used
    to namespace Modal apps, ensuring that sandboxes created by different mngr
    installations on a shared Modal account don't interfere with each other.
    """
    data_dir = mngr_ctx.config.default_host_dir.expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    user_id_file = data_dir / USER_ID_FILENAME

    if user_id_file.exists():
        return user_id_file.read_text().strip()

    # Generate a new user ID
    user_id = uuid4().hex
    user_id_file.write_text(user_id)
    return user_id


class ModalProviderBackend(ProviderBackendInterface):
    """Backend for creating Modal sandbox provider instances.

    The Modal provider backend creates provider instances that manage Modal sandboxes
    as hosts. Each sandbox runs sshd and is accessed via SSH/pyinfra.

    This class maintains a class-level registry of Modal app contexts by app name.
    This ensures we only create one app per unique app_name, even if multiple
    ModalProviderInstance objects are created with the same app_name.
    """

    # Class-level registry of app contexts by app name.
    # Maps app_name -> (modal.App, ModalAppContextHandle)
    _app_registry: ClassVar[dict[str, tuple[modal.App, ModalAppContextHandle]]] = {}

    @classmethod
    def _get_or_create_app(
        cls, app_name: str, environment_name: str, is_persistent: bool
    ) -> tuple[modal.App, ModalAppContextHandle]:
        """Get or create a Modal app with output capture.

        Creates an ephemeral app with `modal.App(name)` and enters its `app.run()`
        context manager. The app is cached in the class-level registry by name, so
        multiple calls with the same app_name will return the same app.

        Modal output is captured via enable_modal_output_capture(), which routes
        all Modal logs to both a StringIO buffer (for inspection) and to loguru
        (for mngr's logging system).

        Also prepares the volume name for state storage. The volume is created
        lazily when first accessed via get_volume_for_app().

        The environment_name is used to scope all Modal resources (apps, volumes,
        sandboxes) to a specific user, enabling isolation between different mngr
        installations sharing the same Modal account.

        Raises modal.exception.AuthError if Modal credentials are not configured.
        """
        if app_name in cls._app_registry:
            return cls._app_registry[app_name]

        logger.debug("Creating ephemeral Modal app with output capture: {} (env: {})", app_name, environment_name)

        # Enter the output capture context first
        output_capture_context = enable_modal_output_capture(is_logging_to_loguru=True)
        output_buffer, loguru_writer = output_capture_context.__enter__()

        if is_persistent:
            # FIXME: make this more clearly a retry after making the environment by using tenacity
            try:
                app = modal.App.lookup(app_name, create_if_missing=True, environment_name=environment_name)
            except modal.exception.NotFoundError:
                # Ensure the environment exists before trying to use it
                _ensure_environment_exists(environment_name)
                app = modal.App.lookup(app_name, create_if_missing=True, environment_name=environment_name)
            run_context = None
        else:
            # Create the Modal app
            app = modal.App(app_name)

            # Enter the app.run() context manager manually so we can return the app
            # while keeping the context active until close() is called
            # FIXME: make this more clearly a retry after making the environment by using tenacity
            try:
                run_context = app.run(environment_name=environment_name)
                run_context.__enter__()
            except modal.exception.NotFoundError:
                # Ensure the environment exists before trying to use it
                _ensure_environment_exists(environment_name)
                run_context = app.run(environment_name=environment_name)
                run_context.__enter__()

        # Set app metadata on the loguru writer for structured logging
        if loguru_writer is not None:
            loguru_writer.app_id = app.app_id
            loguru_writer.app_name = app.name

        # Create the volume name for state storage (volume created lazily)
        volume_name = f"{app_name}{STATE_VOLUME_SUFFIX}"

        context_handle = ModalAppContextHandle(
            run_context=run_context,
            app_name=app_name,
            environment_name=environment_name,
            output_capture_context=output_capture_context,
            output_buffer=output_buffer,
            loguru_writer=loguru_writer,
            volume_name=volume_name,
            volume=None,
        )
        cls._app_registry[app_name] = (app, context_handle)
        return app, context_handle

    @classmethod
    def get_volume_for_app(cls, app_name: str) -> modal.Volume:
        """Get or create the state volume for an app.

        The volume is used to persist host records (including snapshots) across
        sandbox termination. This allows multiple mngr instances to share state
        and enables restoration from snapshots even after the original sandbox
        is gone.

        The volume is created lazily on first access and cached in the context
        handle for subsequent calls. The volume is scoped to the same environment
        as the app.

        Raises MngrError if the app has not been created yet.
        """
        if app_name not in cls._app_registry:
            raise MngrError(f"App {app_name} not found in registry")

        _, context_handle = cls._app_registry[app_name]

        # Return cached volume if already created
        if context_handle.volume is not None:
            return context_handle.volume

        # Create or get the volume in the same environment as the app
        logger.debug(
            "Creating/getting state volume: {} (env: {})", context_handle.volume_name, context_handle.environment_name
        )
        volume = modal.Volume.from_name(
            context_handle.volume_name,
            create_if_missing=True,
            environment_name=context_handle.environment_name,
            version=2,
        )

        # Cache the volume in the context handle (need to update the registry entry)
        # Since FrozenModel is immutable, we need to create a new handle
        updated_handle = ModalAppContextHandle(
            run_context=context_handle.run_context,
            app_name=context_handle.app_name,
            environment_name=context_handle.environment_name,
            output_capture_context=context_handle.output_capture_context,
            output_buffer=context_handle.output_buffer,
            loguru_writer=context_handle.loguru_writer,
            volume_name=context_handle.volume_name,
            volume=volume,
        )
        app, _ = cls._app_registry[app_name]
        cls._app_registry[app_name] = (app, updated_handle)

        return volume

    @classmethod
    def close_app(cls, app_name: str) -> None:
        """Close a Modal app context.

        Exits the app.run() context manager and removes the app from the registry.
        This makes the app ephemeral and prevents accumulation.
        """
        if app_name in cls._app_registry:
            _, context_handle = cls._app_registry.pop(app_name)
            _exit_modal_app_context(context_handle)

    @classmethod
    def reset_app_registry(cls) -> None:
        """Reset the modal app registry.

        Closes all open app contexts and clears the registry. This is primarily used
        for test isolation to ensure a clean state between tests.
        """
        for app_name, (_, context_handle) in list(cls._app_registry.items()):
            try:
                _exit_modal_app_context(context_handle)
            except modal.exception.Error as e:
                logger.debug("Modal error closing app {} during reset: {}", app_name, e)
        cls._app_registry.clear()

    @staticmethod
    def get_name() -> ProviderBackendName:
        return MODAL_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Runs agents in Modal cloud sandboxes with SSH access"

    @staticmethod
    def get_config_class() -> type[ProviderInstanceConfig]:
        return ModalProviderConfig

    @staticmethod
    def get_build_args_help() -> str:
        return """\
Supported build arguments for the modal provider:
  --gpu TYPE        GPU type to use (e.g., t4, a10g, a100, any). Default: no GPU
  --cpu COUNT       Number of CPU cores (0.25-16). Default: 1.0
  --memory GB       Memory in GB (0.5-32). Default: 1.0
  --image NAME      Base Docker image to use. Default: debian:bookworm-slim
  --timeout SEC     Maximum sandbox lifetime in seconds. Default: 900 (15 min)
  --region NAME     Region to run the sandbox in (e.g., us-east, us-west, eu-west). Default: auto
  --context-dir DIR Build context directory for Dockerfile COPY/ADD instructions. Default: Dockerfile's directory
  --secret VAR      Pass an environment variable as a secret to the image build. The value of
                    VAR is read from your current environment and made available during Dockerfile
                    RUN commands via --mount=type=secret,id=VAR. Can be specified multiple times.
"""

    @staticmethod
    def get_start_args_help() -> str:
        return "No start arguments are supported for the modal provider."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        config: ProviderInstanceConfig,
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        """Build a Modal provider instance."""
        assert isinstance(config, ModalProviderConfig)

        # Use prefix + user_id for the environment name, ensuring isolation
        # between different mngr installations sharing the same Modal account.
        # The app name is just prefix + name (no user_id).
        prefix = mngr_ctx.config.prefix
        user_id = _get_or_create_user_id(mngr_ctx)
        environment_name = f"{prefix}{user_id}"
        default_app_name = f"{prefix}{name}"

        # Truncate environment_name if needed to fit Modal's 64 char limit
        if len(environment_name) > MODAL_NAME_MAX_LENGTH:
            logger.warning(
                "Truncating Modal environment name to {} characters: {}", MODAL_NAME_MAX_LENGTH, environment_name
            )
            environment_name = environment_name[:MODAL_NAME_MAX_LENGTH]

        app_name = config.app_name if config.app_name is not None else default_app_name
        host_dir = config.host_dir if config.host_dir is not None else Path("/mngr")

        # Truncate app_name if needed to fit Modal's 64 char limit (accounting for volume suffix)
        max_app_name_length = MODAL_NAME_MAX_LENGTH - len(STATE_VOLUME_SUFFIX)
        if len(app_name) > max_app_name_length:
            logger.warning("Truncating Modal app name to {} characters: {}", max_app_name_length, app_name)
            app_name = app_name[:max_app_name_length]

        # Create the ModalProviderApp that manages the Modal app and its resources
        try:
            app, context_handle = ModalProviderBackend._get_or_create_app(
                app_name, environment_name, config.is_persistent
            )
            volume = ModalProviderBackend.get_volume_for_app(app_name)

            modal_app = ModalProviderApp(
                app_name=app_name,
                environment_name=environment_name,
                app=app,
                volume=volume,
                close_callback=lambda: ModalProviderBackend.close_app(app_name),
                get_output_callback=lambda: context_handle.output_buffer.getvalue(),
            )
        except modal.exception.AuthError as e:
            raise MngrError(
                "Modal is not authorized: run 'modal token set' to authenticate, or disable this provider with "
                f"'mngr config set --scope local providers.{name}.is_enabled false'.",
            ) from e

        return ModalProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
            config=config,
            modal_app=modal_app,
        )


@hookimpl
def register_provider_backend() -> tuple[type[ProviderBackendInterface], type[ProviderInstanceConfig]]:
    """Register the Modal provider backend."""
    return (ModalProviderBackend, ModalProviderConfig)
