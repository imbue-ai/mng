"""SSH provider backend for static host pools.

This provider allows managing hosts by SSH connection. The hosts are statically
configured - the provider does not create or destroy hosts, it simply connects
to pre-existing hosts via SSH.

This is useful for:
- Testing SSH connectivity without cloud providers
- Managing on-premise servers
- Development with local sshd instances
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from imbue.mngr import hookimpl
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.interfaces.provider_backend import ProviderBackendInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ProviderBackendName
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.ssh.instance import SSHHostConfig
from imbue.mngr.providers.ssh.instance import SSHProviderInstance

SSH_BACKEND_NAME = ProviderBackendName("ssh")


class SSHProviderBackend(ProviderBackendInterface):
    """Backend for creating SSH provider instances.

    The SSH provider connects to pre-configured hosts via SSH. Unlike cloud
    providers, it does not create or destroy hosts - they must already exist.

    This provider does not support:
    - Tags (hosts are statically configured)
    - Snapshots (no cloud infrastructure)
    - Creating/destroying hosts (they're pre-existing)
    """

    @staticmethod
    def get_name() -> ProviderBackendName:
        return SSH_BACKEND_NAME

    @staticmethod
    def get_description() -> str:
        return "Connects to pre-configured hosts via SSH (static host pool)"

    @staticmethod
    def get_build_args_help() -> str:
        return """\
The SSH provider does not support creating hosts dynamically.
Hosts must be pre-configured in the mngr config file.

Example configuration in mngr.toml:
  [providers.my-ssh-pool]
  backend = "ssh"

  [providers.my-ssh-pool.hosts.server1]
  address = "192.168.1.100"
  port = 22
  user = "root"
  key_file = "~/.ssh/id_ed25519"
"""

    @staticmethod
    def get_start_args_help() -> str:
        return "No start arguments are supported for the SSH provider."

    @staticmethod
    def build_provider_instance(
        name: ProviderInstanceName,
        instance_configuration: dict[str, Any],
        mngr_ctx: MngrContext,
    ) -> ProviderInstanceInterface:
        """Build an SSH provider instance.

        The instance_configuration should contain:
        - host_dir: Directory for mngr state on remote hosts (default: /tmp/mngr)
        - hosts: dict of host_name -> host configuration
          Each host configuration can have:
          - address: SSH hostname or IP (required)
          - port: SSH port (default: 22)
          - user: SSH username (default: root)
          - key_file: Path to SSH private key (optional)
        """
        # host_dir is the path on remote hosts for mngr state
        host_dir = Path(instance_configuration.get("host_dir", "/tmp/mngr"))
        hosts_config = instance_configuration.get("hosts", {})

        hosts: dict[str, SSHHostConfig] = {}
        for host_name, host_data in hosts_config.items():
            if isinstance(host_data, dict):
                # Convert key_file to Path if present
                if "key_file" in host_data and host_data["key_file"] is not None:
                    host_data = dict(host_data)
                    host_data["key_file"] = Path(host_data["key_file"]).expanduser()
                hosts[host_name] = SSHHostConfig(**host_data)

        return SSHProviderInstance(
            name=name,
            host_dir=host_dir,
            mngr_ctx=mngr_ctx,
            hosts=hosts,
        )


@hookimpl
def register_provider_backend() -> type[ProviderBackendInterface]:
    """Register the SSH provider backend."""
    return SSHProviderBackend
