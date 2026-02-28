"""Core provisioning logic for injecting mng into remote hosts."""

import importlib.metadata
import shlex
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from imbue.imbue_common.logging import log_span
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.primitives import PluginName
from imbue.mng.providers.deploy_utils import collect_deploy_files
from imbue.mng_recursive.data_types import MngInstallMode
from imbue.mng_recursive.data_types import RecursivePluginConfig


def _get_plugin_config(mng_ctx: MngContext) -> RecursivePluginConfig:
    """Get the recursive plugin config from mng context, falling back to defaults."""
    config = mng_ctx.config.plugins.get(PluginName("recursive"))
    if config is not None and isinstance(config, RecursivePluginConfig):
        return config
    return RecursivePluginConfig()


def _get_remote_home(host: OnlineHostInterface) -> str:
    """Get the home directory of the default user on the remote host."""
    result = host.execute_command("echo $HOME")
    if not result.success:
        raise MngError(f"Failed to determine remote home directory: {result.stderr}")
    return result.stdout.strip()


def _resolve_remote_path(dest_path: Path, remote_home: str) -> Path:
    """Resolve a deploy destination path to an absolute path on the remote host.

    Paths starting with '~' are resolved relative to the remote user's home.
    Relative paths are left as-is.
    """
    dest_str = str(dest_path)
    if dest_str.startswith("~"):
        return Path(remote_home) / dest_str.removeprefix("~/")
    return dest_path


def _upload_deploy_files(
    host: OnlineHostInterface,
    deploy_files: dict[Path, Path | str],
    remote_home: str,
) -> int:
    """Upload collected deploy files to the remote host.

    Returns the number of files uploaded.
    """
    count = 0
    for dest_path, source in deploy_files.items():
        resolved_path = _resolve_remote_path(dest_path, remote_home)

        # Ensure parent directory exists
        parent_str = shlex.quote(str(resolved_path.parent))
        host.execute_command(f"mkdir -p {parent_str}")

        # Read content and upload
        if isinstance(source, Path):
            if not source.exists():
                logger.debug("Skipping non-existent deploy file: {}", source)
                continue
            content = source.read_bytes()
            host.write_file(resolved_path, content)
        else:
            host.write_text_file(resolved_path, source)

        logger.trace("Uploaded deploy file: {} -> {}", dest_path, resolved_path)
        count += 1

    return count


def _get_installed_mng_packages() -> list[tuple[str, str]]:
    """Detect which mng packages are installed locally.

    Returns a list of (package_name, version) tuples for all installed
    packages whose names start with 'mng'.
    """
    packages: list[tuple[str, str]] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        version = dist.metadata["Version"]
        if name is not None and version is not None and (name == "mng" or name.startswith("mng-")):
            packages.append((name, version))
    return packages


def _detect_local_install_mode() -> MngInstallMode:
    """Detect whether the local mng installation is editable or a package.

    Returns EDITABLE if installed in development mode, PACKAGE otherwise.
    """
    try:
        dist = importlib.metadata.distribution("mng")
    except importlib.metadata.PackageNotFoundError:
        return MngInstallMode.PACKAGE

    direct_url_text = dist.read_text("direct_url.json")
    if direct_url_text is not None and '"editable": true' in direct_url_text:
        return MngInstallMode.EDITABLE
    return MngInstallMode.PACKAGE


def _resolve_install_mode(mode: MngInstallMode) -> MngInstallMode:
    """Resolve AUTO mode to a concrete install mode."""
    if mode == MngInstallMode.AUTO:
        resolved = _detect_local_install_mode()
        logger.info("Auto-detected mng install mode: {}", resolved.value.lower())
        return resolved
    return mode


def _ensure_uv_available(host: OnlineHostInterface) -> None:
    """Ensure uv is available on the remote host, installing it if necessary."""
    result = host.execute_command("command -v uv")
    if result.success:
        return

    with log_span("Installing uv on remote host"):
        install_result = host.execute_command("curl -LsSf https://astral.sh/uv/install.sh | sh")
        if not install_result.success:
            raise MngError(f"Failed to install uv on remote host: {install_result.stderr.strip()}")
        # Source the cargo env to make uv available in subsequent commands
        host.execute_command('. "$HOME/.local/bin/env" 2>/dev/null || true')


def _is_mng_available_on_host(host: OnlineHostInterface) -> bool:
    """Check if mng is already available on the remote host."""
    result = host.execute_command("command -v mng")
    return result.success


def _get_mng_repo_root() -> Path:
    """Get the git repository root of the mng monorepo.

    Walks up from the mng package source to find the git repo root.
    Raises MngError if not in a git repository.
    """
    try:
        dist = importlib.metadata.distribution("mng")
    except importlib.metadata.PackageNotFoundError:
        raise MngError("mng package is not installed; cannot determine repo root") from None

    direct_url_text = dist.read_text("direct_url.json")
    if direct_url_text is None:
        raise MngError("mng is not installed in editable mode; cannot determine repo root") from None

    # Find the source directory from the editable install
    import json

    direct_url = json.loads(direct_url_text)
    url = direct_url.get("url", "")
    if url.startswith("file://"):
        source_dir = Path(url.removeprefix("file://"))
    else:
        raise MngError(f"Unexpected direct_url format: {url}") from None

    # Find git repo root from source dir
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=source_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MngError(f"Could not find git repo root from {source_dir}: {result.stderr.strip()}") from None
    return Path(result.stdout.strip())


def _install_mng_package_mode(
    host: OnlineHostInterface,
    packages: list[tuple[str, str]],
) -> None:
    """Install mng and plugins from PyPI using uv tool install."""
    mng_package = None
    plugin_packages: list[tuple[str, str]] = []
    for name, version in packages:
        if name == "mng":
            mng_package = (name, version)
        else:
            plugin_packages.append((name, version))

    if mng_package is None:
        raise MngError("mng package not found locally; cannot install on remote host")

    mng_name, mng_version = mng_package
    parts = [f"uv tool install {mng_name}=={mng_version}"]
    for pkg_name, pkg_version in plugin_packages:
        parts.append(f"--with {pkg_name}=={pkg_version}")

    install_cmd = " ".join(parts)
    with log_span("Installing mng (package mode) on remote host"):
        result = host.execute_command(install_cmd)
        if not result.success:
            # Try with --force-reinstall if already installed
            result = host.execute_command(install_cmd + " --force-reinstall")
            if not result.success:
                raise MngError(f"Failed to install mng on remote host: {result.stderr.strip()}")


def _install_mng_editable_mode(
    host: OnlineHostInterface,
) -> None:
    """Install mng from local source in editable mode on the remote host.

    Packages the local mng monorepo into a tarball, uploads it to the
    remote host, extracts it, and installs mng in editable mode.
    """
    repo_root = _get_mng_repo_root()

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball_path = Path(tmpdir) / "mng-repo.tar.gz"

        # Create tarball of the monorepo using git archive
        with log_span("Packaging mng monorepo for transfer"):
            result = subprocess.run(
                ["git", "archive", "--format=tar.gz", "-o", str(tarball_path), "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise MngError(f"Failed to create mng monorepo tarball: {result.stderr.strip()}")

        # Upload tarball to remote host
        remote_tarball = Path("/tmp/mng-repo.tar.gz")
        remote_repo_dir = Path("/tmp/mng-repo")

        with log_span("Uploading mng monorepo to remote host"):
            tarball_content = tarball_path.read_bytes()
            host.write_file(remote_tarball, tarball_content)

        # Extract and install on remote
        with log_span("Installing mng (editable mode) on remote host"):
            extract_cmd = f"rm -rf {remote_repo_dir} && mkdir -p {remote_repo_dir} && tar -xzf {remote_tarball} -C {remote_repo_dir} && rm {remote_tarball}"
            result = host.execute_command(extract_cmd)
            if not result.success:
                raise MngError(f"Failed to extract mng tarball: {result.stderr.strip()}")

            # Build the install command with editable installs for all workspace packages
            # First, discover which libs exist in the tarball
            ls_result = host.execute_command(f"ls {remote_repo_dir}/libs/")
            if not ls_result.success:
                raise MngError(f"Failed to list mng libs: {ls_result.stderr.strip()}")

            lib_names = ls_result.stdout.strip().split()
            install_parts = [f"cd {remote_repo_dir} && uv tool install -e libs/mng"]
            for lib_name in lib_names:
                if lib_name != "mng" and lib_name.startswith("mng_"):
                    install_parts.append(f"--with-editable libs/{lib_name}")

            install_cmd = " ".join(install_parts)
            result = host.execute_command(install_cmd)
            if not result.success:
                # Try with --force-reinstall
                result = host.execute_command(install_cmd + " --force-reinstall")
                if not result.success:
                    raise MngError(f"Failed to install mng in editable mode: {result.stderr.strip()}")


def provision_mng_on_host(
    host: OnlineHostInterface,
    mng_ctx: MngContext,
) -> None:
    """Provision mng config and dependencies on a remote host.

    Skips local hosts (mng is already available). For remote hosts:
    1. Collects deploy files (config, settings, plugin configs) via hooks
    2. Uploads them to the appropriate locations on the remote host
    3. Ensures uv is available (installs if missing)
    4. Installs mng and plugins based on the configured install mode
    """
    if host.is_local:
        logger.debug("Skipping mng provisioning on local host")
        return

    plugin_config = _get_plugin_config(mng_ctx)

    resolved_mode = _resolve_install_mode(plugin_config.install_mode)
    if resolved_mode == MngInstallMode.SKIP:
        logger.debug("Skipping mng provisioning (install_mode=skip)")
        return

    def _handle_error(msg: str, error: Exception) -> None:
        """Handle an error based on the is_errors_fatal setting."""
        if plugin_config.is_errors_fatal:
            raise MngError(msg) from error
        logger.warning("{}: {}", msg, error)

    try:
        with log_span("Provisioning mng on remote host"):
            # Get the remote user's home directory
            remote_home = _get_remote_home(host)

            # Collect and upload deploy files
            repo_root = Path.cwd()
            deploy_files = collect_deploy_files(
                mng_ctx=mng_ctx,
                repo_root=repo_root,
                include_user_settings=True,
                include_project_settings=True,
            )

            if deploy_files:
                with log_span("Uploading {} deploy files to remote host", len(deploy_files)):
                    uploaded = _upload_deploy_files(host, deploy_files, remote_home)
                    logger.info("Uploaded {} mng config files to remote host", uploaded)

            # Ensure uv is available
            _ensure_uv_available(host)

            # Install mng based on the resolved mode
            if resolved_mode == MngInstallMode.PACKAGE:
                packages = _get_installed_mng_packages()
                if packages:
                    _install_mng_package_mode(host, packages)
                else:
                    logger.warning("No mng packages found locally; cannot install on remote host")
            elif resolved_mode == MngInstallMode.EDITABLE:
                _install_mng_editable_mode(host)

    except MngError:
        raise
    except Exception as e:
        _handle_error("Failed to provision mng on remote host", e)
