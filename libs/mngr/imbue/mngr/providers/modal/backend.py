import contextlib
from pathlib import Path
from typing import Any
from typing import ClassVar
from uuid import uuid4

import modal
from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.modal.instance import ModalProviderInstance
from imbue.mngr.providers.modal.log_utils import enable_modal_output_capture

MODAL_BACKEND_NAME = ProviderBackendName("modal")
USER_ID_FILENAME = "user_id"


class ModalAppContextHandle(FrozenModel):
    """Handle for managing a Modal app context lifecycle with output capture.

    This class captures a Modal app's run context along with the output capture
    context. The output buffer can be inspected to detect build failures and
    other issues in the Modal logs.
    """

    run_context: Any = Field(description="The Modal app.run() context manager")
    app_name: str = Field(description="The name of the Modal app")
    output_capture_context: Any = Field(description="The output capture context manager")
    output_buffer: Any = Field(description="StringIO buffer containing captured Modal output")
    loguru_writer: Any = Field(description="Loguru writer for structured logging (or None)")


def _exit_modal_app_context(handle: ModalAppContextHandle) -> None:
    """Exit a Modal app context and its output capture context."""
    logger.debug("Exiting Modal app context: {}", handle.app_name)

    # Log any captured output for debugging
    captured_output = handle.output_buffer.getvalue()
    if captured_output:
        logger.trace("Modal output captured ({} chars): {}", len(captured_output), captured_output[:500])

    # Exit the app context first
    try:
        handle.run_context.__exit__(None, None, None)
    except modal.exception.Error as e:
        logger.warning("Modal error exiting app context {}: {}", handle.app_name, e)

    # Exit the output capture context - this is a cleanup operation so we just
    # suppress any errors
    with contextlib.suppress(OSError, RuntimeError):
        handle.output_capture_context.__exit__(None, None, None)


def _get_or_create_user_id(mngr_ctx: MngrContext) -> str:
    """Get or create a unique user ID for this mngr installation.

    The user ID is stored in a file in the mngr data directory. This ID is used
    to namespace Modal apps, ensuring that sandboxes created by different mngr
    installations on a shared Modal account don't interfere with each other.

    We use only 8 hex characters to keep app names under Modal's 64 char limit.
    """
    data_dir = mngr_ctx.config.default_host_dir.expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    user_id_file = data_dir / USER_ID_FILENAME

    if user_id_file.exists():
        return user_id_file.read_text().strip()

    # Generate a new user ID (8 hex chars for ~4 billion unique values)
    user_id = uuid4().hex[:8]
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
    def _get_or_create_app(cls, app_name: str) -> tuple[modal.App, ModalAppContextHandle]:
        """Get or create a Modal app with output capture.

        Creates an ephemeral app with `modal.App(name)` and enters its `app.run()`
        context manager. The app is cached in the class-level registry by name, so
        multiple calls with the same app_name will return the same app.

        Modal output is captured via enable_modal_output_capture(), which routes
        all Modal logs to both a StringIO buffer (for inspection) and to loguru
        (for mngr's logging system).

        Raises modal.exception.AuthError if Modal credentials are not configured.
        """
        if app_name in cls._app_registry:
            return cls._app_registry[app_name]

        logger.debug("Creating ephemeral Modal app with output capture: {}", app_name)

        # Enter the output capture context first
        output_capture_context = enable_modal_output_capture(is_logging_to_loguru=True)
        output_buffer, loguru_writer = output_capture_context.__enter__()

        # Create the Modal app
        app = modal.App(app_name)

        # Enter the app.run() context manager manually so we can return the app
        # while keeping the context active until close() is called
        run_context = app.run()
        run_context.__enter__()

        # Set app metadata on the loguru writer for structured logging
        if loguru_writer is not None:
            loguru_writer.app_id = app.app_id
            loguru_writer.app_name = app.name

        context_handle = ModalAppContextHandle(
            run_context=run_context,
            app_name=app_name,
            output_capture_context=output_capture_context,
            output_buffer=output_buffer,
            loguru_writer=loguru_writer,
        )
        cls._app_registry[app_name] = (app, context_handle)
        return app, context_handle

    @classmethod
    def get_captured_output_for_app(cls, app_name: str) -> str:
        """Get all captured Modal output for an app.

        Returns the contents of the output buffer that has been capturing Modal
        logs since the app was created. This can be used to detect build failures
        or other issues by inspecting the captured output.

        Returns an empty string if no app has been created with the given name.
        """
        if app_name not in cls._app_registry:
            return ""
        _, context_handle = cls._app_registry[app_name]
        return context_handle.output_buffer.getvalue()

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
    def get_build_args_help() -> str:
        return """\
Supported build arguments for the modal provider:
  --gpu TYPE    GPU type to use (e.g., t4, a10g, a100, any). Default: no GPU
  --cpu COUNT   Number of CPU cores (0.25-16). Default: 1.0
  --memory GB   Memory in GB (0.5-32). Default: 1.0
  --image NAME  Base Docker image to use. Default: debian:bookworm-slim
  --timeout SEC Maximum sandbox lifetime in seconds. Default: 900 (15 min)
"""

    @staticmethod
    def get_start_args_help() -> str:
        return "No start arguments are supported for the modal provider."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        instance_configuration: dict[str, Any],
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        """Build a Modal provider instance.

        The instance_configuration may contain:
        - app_name: Modal app name (defaults to "mngr-{name}")
        - host_dir: Base directory for mngr data on the sandbox (defaults to /mngr)
        - default_timeout: Default sandbox timeout in seconds (defaults to 900)
        - default_cpu: Default CPU cores (defaults to 1.0)
        - default_memory: Default memory in GB (defaults to 1.0)
        """
        # Use prefix + user_id + name to namespace the app, ensuring isolation
        # between different mngr installations sharing the same Modal account
        prefix = mngr_ctx.config.prefix
        user_id = _get_or_create_user_id(mngr_ctx)
        default_app_name = f"{prefix}{user_id}-{name}"
        app_name = instance_configuration.get("app_name", default_app_name)
        host_dir = Path(instance_configuration.get("host_dir", "/mngr"))
        default_timeout = instance_configuration.get("default_timeout", 900)
        default_cpu = instance_configuration.get("default_cpu", 1.0)
        default_memory = instance_configuration.get("default_memory", 1.0)

        return ModalProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
            app_name=app_name,
            default_timeout=default_timeout,
            default_cpu=default_cpu,
            default_memory=default_memory,
            # Pass the backend class so instance can call its methods
            backend_cls=ModalProviderBackend,
        )


@hookimpl
def register_provider_backend() -> type[ProviderBackendInterface]:
    """Register the Modal provider backend."""
    return ModalProviderBackend
