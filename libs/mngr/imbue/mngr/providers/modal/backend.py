from pathlib import Path
from typing import Any
from uuid import uuid4

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.modal.instance import ModalProviderInstance

MODAL_BACKEND_NAME = ProviderBackendName("modal")
USER_ID_FILENAME = "user_id"


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
    """

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
        )


@hookimpl
def register_provider_backend() -> type[ProviderBackendInterface]:
    """Register the Modal provider backend."""
    return ModalProviderBackend
