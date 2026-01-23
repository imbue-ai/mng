"""Utilities for copying work directories between hosts.

This module provides functionality for copying source directories to destination
hosts, supporting both git-based and rsync-based copying strategies.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from loguru import logger

from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.host import AgentGitOptions
from imbue.mngr.interfaces.host import HostInterface
from imbue.mngr.interfaces.host import SourceDataOptions


def copy_work_dir(
    source_host: HostInterface,
    source_path: Path,
    target_host: HostInterface,
    target_path: Path,
    git_options: AgentGitOptions,
    data_options: SourceDataOptions,
) -> None:
    """Copy a work directory from source host to target host.

    Uses git clone if the source has a git repo and git options are specified,
    otherwise uses rsync.
    """
    # Determine if source is a git repo
    source_has_git = _is_git_repo(source_host, source_path)

    # Check if git-specific options are requested but source has no git repo
    has_git_specific_options = (
        git_options.depth is not None
        or git_options.shallow_since is not None
        or git_options.base_branch is not None
        or git_options.is_new_branch
    )

    if has_git_specific_options and not source_has_git:
        raise UserInputError(
            f"Git options were specified (depth={git_options.depth}, "
            f"shallow_since={git_options.shallow_since}, "
            f"base_branch={git_options.base_branch}), "
            f"but source path {source_path} is not a git repository"
        )

    # Determine if both hosts are local
    both_local = source_host.is_local and target_host.is_local
    source_is_local = source_host.is_local
    target_is_local = target_host.is_local

    if source_has_git and data_options.is_include_git:
        # Use git-based copy
        _copy_with_git(
            source_host=source_host,
            source_path=source_path,
            target_host=target_host,
            target_path=target_path,
            git_options=git_options,
            data_options=data_options,
            both_local=both_local,
            source_is_local=source_is_local,
            target_is_local=target_is_local,
        )
    else:
        # Use rsync-based copy
        _copy_with_rsync(
            source_host=source_host,
            source_path=source_path,
            target_host=target_host,
            target_path=target_path,
            data_options=data_options,
            both_local=both_local,
            source_is_local=source_is_local,
            target_is_local=target_is_local,
        )


def _is_git_repo(host: HostInterface, path: Path) -> bool:
    """Check if the given path is a git repository."""
    git_dir = path / ".git"
    result = host.execute_command(f"test -d {shlex.quote(str(git_dir))}")
    return result.success


def _get_ssh_user_host(host: HostInterface) -> str | None:
    """Get the SSH user@host string for a remote host.

    Returns None if the host is local.
    """
    if host.is_local:
        return None

    pyinfra_host = host.connector.host
    ssh_host = pyinfra_host.name
    ssh_user = pyinfra_host.data.get("ssh_user")

    if ssh_user:
        return f"{ssh_user}@{ssh_host}"
    return ssh_host


def _get_ssh_options(host: HostInterface) -> list[str]:
    """Get SSH options for connecting to a remote host."""
    if host.is_local:
        return []

    pyinfra_host = host.connector.host
    ssh_port = pyinfra_host.data.get("ssh_port")
    ssh_key = pyinfra_host.data.get("ssh_key")
    ssh_known_hosts_file = pyinfra_host.data.get("ssh_known_hosts_file")

    options: list[str] = []

    if ssh_key:
        options.extend(["-i", str(ssh_key)])

    if ssh_port:
        options.extend(["-p", str(ssh_port)])

    if ssh_known_hosts_file and ssh_known_hosts_file != "/dev/null":
        options.extend(["-o", f"UserKnownHostsFile={ssh_known_hosts_file}"])
        options.extend(["-o", "StrictHostKeyChecking=yes"])

    return options


def _copy_with_git(
    source_host: HostInterface,
    source_path: Path,
    target_host: HostInterface,
    target_path: Path,
    git_options: AgentGitOptions,
    data_options: SourceDataOptions,
    both_local: bool,
    source_is_local: bool,
    target_is_local: bool,
) -> None:
    """Copy a git repository using git clone.

    Uses git clone with appropriate options for depth, shallow_since, etc.
    """
    logger.debug(
        "Copying git repository from {}:{} to {}:{}",
        "local" if source_is_local else "remote",
        source_path,
        "local" if target_is_local else "remote",
        target_path,
    )

    # Build the clone command
    clone_args: list[str] = ["git", "clone"]

    # Add depth options
    if git_options.depth is not None:
        clone_args.extend(["--depth", str(git_options.depth)])

    if git_options.shallow_since is not None:
        clone_args.extend(["--shallow-since", git_options.shallow_since])

    # Add branch option if specified
    if git_options.base_branch is not None:
        clone_args.extend(["--branch", git_options.base_branch])

    # Determine the source URL
    if both_local:
        # Local to local: use file:// protocol to enable shallow clones
        # Note: shallow clones (--depth) don't work with bare paths, only file://
        source_url = f"file://{source_path}"
        _run_git_clone_local(target_host, clone_args, source_url, target_path)
    elif source_is_local and not target_is_local:
        # Local to remote: use git push to a new repo
        _run_git_push_to_remote(
            source_host,
            source_path,
            target_host,
            target_path,
            git_options,
        )
    elif not source_is_local and target_is_local:
        # Remote to local: clone via SSH
        ssh_user_host = _get_ssh_user_host(source_host)
        source_url = f"{ssh_user_host}:{source_path}"
        _run_git_clone_local_with_remote_source(
            target_host, clone_args, source_url, target_path, source_host
        )
    else:
        # Remote to remote: this case is more complex
        # For now, use rsync as fallback
        logger.debug("Remote to remote git copy not supported, falling back to rsync")
        _copy_with_rsync(
            source_host=source_host,
            source_path=source_path,
            target_host=target_host,
            target_path=target_path,
            data_options=data_options,
            both_local=both_local,
            source_is_local=source_is_local,
            target_is_local=target_is_local,
        )


def _run_git_clone_local(
    target_host: HostInterface,
    clone_args: list[str],
    source_url: str,
    target_path: Path,
) -> None:
    """Run git clone on the target host (both local case)."""
    clone_args.append(shlex.quote(source_url))
    clone_args.append(shlex.quote(str(target_path)))

    cmd = " ".join(clone_args)
    logger.debug("Running git clone: {}", cmd)

    result = target_host.execute_command(cmd)
    if not result.success:
        raise MngrError(f"Git clone failed: {result.stderr}")


def _run_git_clone_local_with_remote_source(
    target_host: HostInterface,
    clone_args: list[str],
    source_url: str,
    target_path: Path,
    source_host: HostInterface,
) -> None:
    """Run git clone on the target host with a remote source."""
    # Build SSH command for git
    ssh_options = _get_ssh_options(source_host)
    if ssh_options:
        ssh_cmd = "ssh " + " ".join(shlex.quote(opt) for opt in ssh_options)
        clone_args.extend(["--config", f"core.sshCommand={shlex.quote(ssh_cmd)}"])

    clone_args.append(shlex.quote(source_url))
    clone_args.append(shlex.quote(str(target_path)))

    cmd = " ".join(clone_args)
    logger.debug("Running git clone with remote source: {}", cmd)

    result = target_host.execute_command(cmd)
    if not result.success:
        raise MngrError(f"Git clone failed: {result.stderr}")


def _run_git_push_to_remote(
    source_host: HostInterface,
    source_path: Path,
    target_host: HostInterface,
    target_path: Path,
    git_options: AgentGitOptions,
) -> None:
    """Push a git repository from local source to remote target.

    This creates a bare repository on the remote, pushes to it, and then
    checks out the working directory.
    """
    # First, create the target directory
    target_host.execute_command(f"mkdir -p {shlex.quote(str(target_path))}")

    # Initialize a bare repository on the remote
    result = target_host.execute_command(
        f"git init --bare {shlex.quote(str(target_path))}/.git.tmp"
    )
    if not result.success:
        raise MngrError(f"Failed to initialize remote git repo: {result.stderr}")

    # Get SSH options for the push
    ssh_user_host = _get_ssh_user_host(target_host)
    ssh_options = _get_ssh_options(target_host)

    # Build the remote URL
    remote_url = f"{ssh_user_host}:{target_path}/.git.tmp"

    # Build and run the git push command
    push_cmd_parts = ["git", "-C", shlex.quote(str(source_path)), "push"]

    # Configure SSH command if needed
    env_prefix = ""
    if ssh_options:
        ssh_cmd = "ssh " + " ".join(shlex.quote(opt) for opt in ssh_options)
        env_prefix = f"GIT_SSH_COMMAND={shlex.quote(ssh_cmd)} "

    # Determine which branches to push
    branch_to_push = git_options.base_branch if git_options.base_branch else "HEAD"
    push_cmd_parts.extend([shlex.quote(remote_url), f"{branch_to_push}:refs/heads/main"])

    push_cmd = env_prefix + " ".join(push_cmd_parts)
    logger.debug("Running git push: {}", push_cmd)

    result = source_host.execute_command(push_cmd)
    if not result.success:
        raise MngrError(f"Git push failed: {result.stderr}")

    # Convert to a non-bare repository on the remote
    # Move .git.tmp to .git and checkout
    setup_cmd = (
        f"cd {shlex.quote(str(target_path))} && "
        f"mv .git.tmp .git && "
        f"git config --local --bool core.bare false && "
        f"git checkout -f"
    )

    result = target_host.execute_command(setup_cmd)
    if not result.success:
        raise MngrError(f"Failed to set up remote working directory: {result.stderr}")


def _copy_with_rsync(
    source_host: HostInterface,
    source_path: Path,
    target_host: HostInterface,
    target_path: Path,
    data_options: SourceDataOptions,
    both_local: bool,
    source_is_local: bool,
    target_is_local: bool,
) -> None:
    """Copy a directory using rsync.

    This is used for non-git directories or when git options are not needed.
    """
    logger.debug(
        "Copying with rsync from {}:{} to {}:{}",
        "local" if source_is_local else "remote",
        source_path,
        "local" if target_is_local else "remote",
        target_path,
    )

    # Build rsync command
    rsync_args: list[str] = ["rsync", "-a", "--delete"]

    # Add exclude patterns
    for pattern in data_options.exclude_patterns:
        rsync_args.extend(["--exclude", pattern])

    # Exclude .git if not including git
    if not data_options.is_include_git:
        rsync_args.extend(["--exclude", ".git"])

    # Handle include patterns (rsync --include requires careful ordering)
    for pattern in data_options.include_patterns:
        rsync_args.extend(["--include", pattern])

    # Determine source and destination based on host types
    if both_local:
        # Local to local
        source_spec = str(source_path) + "/"
        dest_spec = str(target_path) + "/"
        executing_host = source_host
        rsync_shell_opt = None
    elif source_is_local and not target_is_local:
        # Local to remote - use tar over ssh (doesn't require rsync on remote)
        _copy_local_to_remote_with_tar(
            source_host=source_host,
            source_path=source_path,
            target_host=target_host,
            target_path=target_path,
            data_options=data_options,
        )
        return
    elif not source_is_local and target_is_local:
        # Remote to local
        ssh_user_host = _get_ssh_user_host(source_host)
        source_spec = f"{ssh_user_host}:{source_path}/"
        dest_spec = str(target_path) + "/"
        executing_host = target_host
        rsync_shell_opt = _build_rsync_ssh_option(source_host)
    else:
        # Remote to remote - not directly supported by rsync
        # Could implement by piping through local, but for now just error
        raise MngrError(
            "Remote-to-remote copy is not yet supported. "
            "Please use an intermediate local copy."
        )

    if rsync_shell_opt:
        rsync_args.extend(["-e", rsync_shell_opt])

    rsync_args.append(source_spec)
    rsync_args.append(dest_spec)

    # Create target directory first
    if target_is_local:
        target_host.execute_command(f"mkdir -p {shlex.quote(str(target_path))}")
    else:
        target_host.execute_command(f"mkdir -p {shlex.quote(str(target_path))}")

    # Run rsync
    cmd = " ".join(shlex.quote(arg) for arg in rsync_args)
    logger.debug("Running rsync: {}", cmd)

    result = executing_host.execute_command(cmd)
    if not result.success:
        raise MngrError(f"Rsync failed: {result.stderr}")


def _build_rsync_ssh_option(remote_host: HostInterface) -> str:
    """Build the SSH command string for rsync -e option."""
    ssh_options = _get_ssh_options(remote_host)
    if not ssh_options:
        return "ssh"

    return "ssh " + " ".join(shlex.quote(opt) for opt in ssh_options)


def _copy_local_to_remote_with_tar(
    source_host: HostInterface,
    source_path: Path,
    target_host: HostInterface,
    target_path: Path,
    data_options: SourceDataOptions,
) -> None:
    """Copy files from local to remote using tar over ssh.

    This method doesn't require rsync on the remote host, only tar and ssh.
    """
    logger.debug(
        "Copying with tar+ssh from local:{} to remote:{}",
        source_path,
        target_path,
    )

    # Build exclude args for tar
    exclude_args: list[str] = []
    for pattern in data_options.exclude_patterns:
        exclude_args.extend(["--exclude", pattern])
    if not data_options.is_include_git:
        exclude_args.extend(["--exclude", ".git"])

    # Build the SSH command
    ssh_user_host = _get_ssh_user_host(target_host)
    ssh_options = _get_ssh_options(target_host)
    ssh_cmd_parts = ["ssh"]
    ssh_cmd_parts.extend(ssh_options)
    ssh_cmd_parts.append(shlex.quote(str(ssh_user_host)))

    # Build the tar create command (runs locally)
    tar_create = ["tar", "-C", shlex.quote(str(source_path)), "-cz"]
    tar_create.extend(shlex.quote(arg) for arg in exclude_args)
    tar_create.append(".")

    # Build the remote command: mkdir + tar extract
    remote_cmd = f"mkdir -p {shlex.quote(str(target_path))} && tar -C {shlex.quote(str(target_path))} -xz"

    # Combine: tar cz | ssh remote "mkdir -p target && tar xz"
    full_cmd = " ".join(tar_create) + " | " + " ".join(ssh_cmd_parts) + " " + shlex.quote(remote_cmd)

    logger.debug("Running tar+ssh: {}", full_cmd)

    result = source_host.execute_command(full_cmd)
    if not result.success:
        raise MngrError(f"Tar+ssh copy failed: {result.stderr}")
