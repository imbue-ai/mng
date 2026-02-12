import shutil
import subprocess
from pathlib import Path

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mngr.plugins.port_forwarding.config_generation import generate_frps_config
from imbue.mngr.plugins.port_forwarding.data_types import PortForwardingConfig


def ensure_frps_config(config: PortForwardingConfig) -> Path:
    """Write the frps config file to disk and return its path."""
    config_path = Path(config.frps_config_path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_content = generate_frps_config(config)
    config_path.write_text(config_content)
    config_path.chmod(0o600)
    return config_path


def is_frps_installed() -> bool:
    """Check if frps is available on PATH."""
    return shutil.which("frps") is not None


def is_frps_running(config: PortForwardingConfig) -> bool:
    """Check if frps is already listening on the configured bind port."""
    result = subprocess.run(
        ["lsof", "-i", f":{config.frps_bind_port}", "-sTCP:LISTEN"],
        capture_output=True,
        timeout=5,
    )
    return result.returncode == 0


def start_frps(config: PortForwardingConfig) -> None:
    """Start frps as a background daemon process."""
    if not is_frps_installed():
        logger.warning("frps is not installed; port forwarding will not work")
        return

    if is_frps_running(config):
        logger.debug("frps is already running on port {}", config.frps_bind_port)
        return

    config_path = ensure_frps_config(config)

    with log_span("Starting frps on port {}", config.frps_bind_port):
        subprocess.Popen(
            ["frps", "-c", str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    logger.debug("Started frps (bind={}, vhost={})", config.frps_bind_port, config.vhost_http_port)
