from pathlib import Path
from typing import Final

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.plugins.port_forwarding.config_generation import generate_frpc_base_config
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig
from imbue.mngr.plugins.port_forwarding.forward_service_script import generate_forward_service_script

FRPC_CONFIG_DIR: Final[str] = "/etc/frpc"
FORWARD_SERVICE_PATH: Final[str] = "/usr/local/bin/forward-service"


def install_frpc_on_host(
    host: OnlineHostInterface,
    config: PortForwardingConfig,
) -> None:
    """Install frpc and the forward-service script on a remote host."""
    with log_span("Installing frpc on host {}", host.get_name()):
        # Check if frpc is already installed
        check_result = host.execute_command("command -v frpc", timeout_seconds=5.0)
        if not check_result.success:
            # Install frpc via the official install script
            install_cmd = (
                "curl -fsSL https://raw.githubusercontent.com/fatedier/frp/dev/hack/install.sh | bash -s -- -t client"
            )
            result = host.execute_command(install_cmd, user="root", timeout_seconds=120.0)
            if not result.success:
                logger.warning("Failed to install frpc on host {}: {}", host.get_name(), result.stderr)
                return

    with log_span("Configuring frpc on host {}", host.get_name()):
        # Create frpc config directory
        host.execute_command(f"mkdir -p {FRPC_CONFIG_DIR}/proxies", user="root", timeout_seconds=5.0)

        # Write base frpc config (connects to frps via localhost reverse tunnel)
        frpc_base = generate_frpc_base_config(
            frps_address="127.0.0.1",
            frps_port=int(config.frps_bind_port),
            frps_token=config.frps_token.get_secret_value(),
        )
        # Add includes directive so proxy fragments are picked up
        frpc_config_content = frpc_base + f'\nincludes = ["{FRPC_CONFIG_DIR}/proxies/*.toml"]\n'

        host.write_text_file(Path(f"{FRPC_CONFIG_DIR}/frpc.toml"), frpc_config_content, mode="0600")

    with log_span("Installing forward-service script on host {}", host.get_name()):
        script_content = generate_forward_service_script(
            domain_suffix=config.domain_suffix,
            vhost_port=int(config.vhost_http_port),
            frpc_config_dir=FRPC_CONFIG_DIR,
        )

        host.write_text_file(Path(FORWARD_SERVICE_PATH), script_content, mode="0755")

    logger.debug("Port forwarding provisioning complete for host {}", host.get_name())
