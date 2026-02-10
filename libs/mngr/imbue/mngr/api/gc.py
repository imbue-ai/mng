import shlex
import shutil
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from loguru import logger

from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.model_update import to_update
from imbue.mngr.api.data_types import GcResourceTypes
from imbue.mngr.api.data_types import GcResult
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.data_types import BuildCacheInfo
from imbue.mngr.interfaces.data_types import HostInfo
from imbue.mngr.interfaces.data_types import LogFileInfo
from imbue.mngr.interfaces.data_types import SizeBytes
from imbue.mngr.interfaces.data_types import WorkDirInfo
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.interfaces.provider_instance import ProviderInstanceInterface
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.utils.cel_utils import apply_cel_filters_to_context
from imbue.mngr.utils.cel_utils import compile_cel_filters


@log_call
def gc(
    mngr_ctx: MngrContext,
    providers: Sequence[ProviderInstanceInterface],
    resource_types: GcResourceTypes,
    # CEL expressions - only include resources matching these
    include_filters: tuple[str, ...],
    # CEL expressions - exclude resources matching these
    exclude_filters: tuple[str, ...],
    # If True, identify but don't destroy resources
    dry_run: bool,
    # Whether to abort or continue on errors
    error_behavior: ErrorBehavior,
) -> GcResult:
    """Run garbage collection on specified resources across providers.

    Identifies and optionally destroys unused resources including:
    - Orphaned work directories
    - Idle machines with no agents
    - Orphaned snapshots
    - Orphaned volumes
    - Old log files
    - Build cache entries
    """
    result = GcResult()
    logger.trace("Configured GC: dry_run={} error_behavior={}", dry_run, error_behavior)

    if resource_types.is_work_dirs:
        with log_span("Garbage collecting orphaned work directories"):
            gc_work_dirs(
                mngr_ctx=mngr_ctx,
                providers=providers,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                dry_run=dry_run,
                error_behavior=error_behavior,
                result=result,
            )

    if resource_types.is_machines:
        with log_span("Garbage collecting idle machines"):
            gc_machines(
                providers=providers,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                dry_run=dry_run,
                error_behavior=error_behavior,
                result=result,
            )

    if resource_types.is_snapshots:
        with log_span("Garbage collecting orphaned snapshots"):
            gc_snapshots(
                providers=providers,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                dry_run=dry_run,
                error_behavior=error_behavior,
                result=result,
            )

    if resource_types.is_volumes:
        with log_span("Garbage collecting orphaned volumes"):
            gc_volumes(
                providers=providers,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                dry_run=dry_run,
                error_behavior=error_behavior,
                result=result,
            )

    if resource_types.is_logs:
        with log_span("Garbage collecting old log files"):
            gc_logs(
                mngr_ctx=mngr_ctx,
                providers=providers,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                dry_run=dry_run,
                error_behavior=error_behavior,
                result=result,
            )

    if resource_types.is_build_cache:
        with log_span("Garbage collecting build cache entries"):
            gc_build_cache(
                mngr_ctx=mngr_ctx,
                providers=providers,
                include_filters=include_filters,
                exclude_filters=exclude_filters,
                dry_run=dry_run,
                error_behavior=error_behavior,
                result=result,
            )

    return result


def gc_work_dirs(
    mngr_ctx: MngrContext,
    providers: Sequence[ProviderInstanceInterface],
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    dry_run: bool,
    error_behavior: ErrorBehavior,
    result: GcResult,
) -> None:
    """Garbage collect orphaned work directories."""
    compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    for provider_instance in providers:
        logger.trace("Checked provider {} for orphaned work directories", provider_instance.name)
        for host in provider_instance.list_hosts():
            logger.trace("Checked host {} for orphaned work directories", host.id)

            if not isinstance(host, OnlineHostInterface):
                # Skip offline hosts - can't query them
                logger.trace("Skipped work dir GC because host is offline", host_id=host.id)
            else:
                # otherwise is online
                try:
                    orphaned_dirs = _get_orphaned_work_dirs(host=host, provider_name=provider_instance.name)
                except HostOfflineError:
                    logger.trace("Skipped work dir GC because host is offline", host_id=host.id)
                    continue

                # Apply CEL filtering
                filtered_dirs = [
                    d
                    for d in orphaned_dirs
                    if (not compiled_include_filters or _apply_cel_filters(d, compiled_include_filters, []))
                    and (not compiled_exclude_filters or _apply_cel_filters(d, [], compiled_exclude_filters))
                ]

                for work_dir_info in filtered_dirs:
                    try:
                        if not dry_run:
                            _clean_work_dir(host=host, work_dir_path=work_dir_info.path, dry_run=False)
                        result.work_dirs_destroyed.append(work_dir_info)
                    except MngrError as e:
                        error_msg = f"Failed to clean {work_dir_info.path}: {e}"
                        result.errors.append(error_msg)
                        _handle_error(error_msg, error_behavior, exc=e)


def gc_machines(
    providers: Sequence[ProviderInstanceInterface],
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    dry_run: bool,
    error_behavior: ErrorBehavior,
    result: GcResult,
) -> None:
    """Garbage collect idle machines with no agents."""
    compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    for provider in providers:
        logger.trace("Checked provider {} for idle machines", provider.name)
        try:
            hosts = provider.list_hosts(include_destroyed=False)

            for host in hosts:
                try:
                    # Skip offline hosts - can't query them
                    if not isinstance(host, OnlineHostInterface):
                        continue

                    # Skip local hosts - they cannot be destroyed
                    if host.is_local:
                        continue

                    agent_refs = host.get_agent_references()

                    # Only consider hosts with no agents
                    if len(agent_refs) > 0:
                        continue

                    host_info = HostInfo(
                        id=host.id,
                        name=str(host.id),
                        provider_name=provider.name,
                    )

                    # Apply CEL filtering
                    if compiled_include_filters or compiled_exclude_filters:
                        if not (
                            (
                                not compiled_include_filters
                                or _apply_cel_filters(host_info, compiled_include_filters, [])
                            )
                            and (
                                not compiled_exclude_filters
                                or _apply_cel_filters(host_info, [], compiled_exclude_filters)
                            )
                        ):
                            continue

                    if not dry_run:
                        provider.destroy_host(host, delete_snapshots=False)

                    result.machines_destroyed.append(host_info)

                except MngrError as e:
                    error_msg = f"Failed to check/destroy host {host.id}: {e}"
                    result.errors.append(error_msg)
                    _handle_error(error_msg, error_behavior, exc=e)

        except MngrError as e:
            error_msg = f"Failed to list hosts for provider {provider.name}: {e}"
            result.errors.append(error_msg)
            _handle_error(error_msg, error_behavior, exc=e)


def gc_snapshots(
    providers: Sequence[ProviderInstanceInterface],
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    dry_run: bool,
    error_behavior: ErrorBehavior,
    result: GcResult,
) -> None:
    """Garbage collect orphaned snapshots."""
    compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    for provider in providers:
        if not provider.supports_snapshots:
            logger.trace("Skipped provider {} (does not support snapshots)", provider.name)
            continue

        logger.trace("Checked provider {} for orphaned snapshots", provider.name)
        try:
            hosts = provider.list_hosts(include_destroyed=False)

            for host in hosts:
                try:
                    snapshots = provider.list_snapshots(host)

                    # Sort by creation time (newest first) and assign recency_idx
                    sorted_snapshots = sorted(snapshots, key=lambda s: s.created_at, reverse=True)
                    snapshots_with_recency = [
                        snapshot.model_copy_update(
                            to_update(snapshot.field_ref().recency_idx, idx),
                        )
                        for idx, snapshot in enumerate(sorted_snapshots)
                    ]

                    # Apply CEL filtering
                    filtered_snapshots = snapshots_with_recency
                    if compiled_include_filters or compiled_exclude_filters:
                        filtered_snapshots = [
                            s
                            for s in snapshots_with_recency
                            if (not compiled_include_filters or _apply_cel_filters(s, compiled_include_filters, []))
                            and (not compiled_exclude_filters or _apply_cel_filters(s, [], compiled_exclude_filters))
                        ]

                    for snapshot in filtered_snapshots:
                        if not dry_run:
                            provider.delete_snapshot(host, snapshot.id)

                        result.snapshots_destroyed.append(snapshot)

                except MngrError as e:
                    error_msg = f"Failed to cleanup snapshots for host {host.id}: {e}"
                    result.errors.append(error_msg)
                    _handle_error(error_msg, error_behavior, exc=e)

        except MngrError as e:
            error_msg = f"Failed to process snapshots for provider {provider.name}: {e}"
            result.errors.append(error_msg)
            _handle_error(error_msg, error_behavior, exc=e)


def gc_volumes(
    providers: Sequence[ProviderInstanceInterface],
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    dry_run: bool,
    error_behavior: ErrorBehavior,
    result: GcResult,
) -> None:
    """Garbage collect orphaned volumes."""
    compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    for provider in providers:
        if not provider.supports_volumes:
            logger.trace("Skipped provider {} (does not support volumes)", provider.name)
            continue

        logger.trace("Checked provider {} for orphaned volumes", provider.name)
        try:
            # Get all volumes
            all_volumes = provider.list_volumes()

            # Get volumes that are currently attached to hosts
            active_volume_ids = set()
            for host in provider.list_hosts(include_destroyed=False):
                for volume in all_volumes:
                    if volume.host_id == host.id:
                        active_volume_ids.add(volume.volume_id)

            # Identify orphaned volumes
            orphaned_volumes = [v for v in all_volumes if v.volume_id not in active_volume_ids]

            # Apply CEL filtering
            filtered_volumes = orphaned_volumes
            if compiled_include_filters or compiled_exclude_filters:
                filtered_volumes = [
                    v
                    for v in filtered_volumes
                    if (not compiled_include_filters or _apply_cel_filters(v, compiled_include_filters, []))
                    and (not compiled_exclude_filters or _apply_cel_filters(v, [], compiled_exclude_filters))
                ]

            for volume in filtered_volumes:
                try:
                    if not dry_run:
                        provider.delete_volume(volume.volume_id)

                    result.volumes_destroyed.append(volume)

                except MngrError as e:
                    error_msg = f"Failed to delete volume {volume.name}: {e}"
                    result.errors.append(error_msg)
                    _handle_error(error_msg, error_behavior, exc=e)

        except MngrError as e:
            error_msg = f"Failed to process volumes for provider {provider.name}: {e}"
            result.errors.append(error_msg)
            _handle_error(error_msg, error_behavior, exc=e)


def gc_logs(
    mngr_ctx: MngrContext,
    providers: Sequence[ProviderInstanceInterface],
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    dry_run: bool,
    error_behavior: ErrorBehavior,
    result: GcResult,
) -> None:
    """Garbage collect old log files."""
    compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    # Construct logs directory from config
    log_dir = mngr_ctx.config.logging.log_dir
    if not log_dir.is_absolute():
        logs_dir = mngr_ctx.config.default_host_dir.expanduser() / log_dir
    else:
        logs_dir = log_dir
    logs_dir = logs_dir.expanduser()

    if not logs_dir.exists():
        logger.trace("Skipped logs directory {} (does not exist)", logs_dir)
        return

    logger.trace("Scanned logs directory {}", logs_dir)

    for log_file in logs_dir.rglob("*"):
        if not log_file.is_file():
            continue

        try:
            stat = log_file.stat()
            file_size = SizeBytes(stat.st_size)
            created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
            log_file_info = LogFileInfo(path=log_file, size_bytes=file_size, created_at=created_at)

            # Apply CEL filtering
            if compiled_include_filters or compiled_exclude_filters:
                if not (
                    (not compiled_include_filters or _apply_cel_filters(log_file_info, compiled_include_filters, []))
                    and (
                        not compiled_exclude_filters or _apply_cel_filters(log_file_info, [], compiled_exclude_filters)
                    )
                ):
                    continue

            if not dry_run:
                log_file.unlink()

            result.logs_destroyed.append(log_file_info)

        except MngrError as e:
            error_msg = f"Failed to delete log {log_file}: {e}"
            result.errors.append(error_msg)
            _handle_error(error_msg, error_behavior, exc=e)


def gc_build_cache(
    mngr_ctx: MngrContext,
    providers: Sequence[ProviderInstanceInterface],
    include_filters: tuple[str, ...],
    exclude_filters: tuple[str, ...],
    dry_run: bool,
    error_behavior: ErrorBehavior,
    result: GcResult,
) -> None:
    """Garbage collect build cache entries."""
    compiled_include_filters, compiled_exclude_filters = compile_cel_filters(include_filters, exclude_filters)

    # Construct providers directory from profile
    base_cache_dir = mngr_ctx.profile_dir / "providers"

    if not base_cache_dir.exists():
        logger.trace("Skipped build cache directory {} (does not exist)", base_cache_dir)
        return

    logger.trace("Scanned build cache directory {}", base_cache_dir)

    for provider_dir in base_cache_dir.iterdir():
        if not provider_dir.is_dir():
            continue

        cache_dir = provider_dir / "cache"
        if not cache_dir.exists():
            continue

        # Clean up build cache entries
        for cache_entry in cache_dir.rglob("*"):
            if not cache_entry.is_dir():
                continue

            try:
                # Calculate size
                cache_entry_size = SizeBytes(sum(f.stat().st_size for f in cache_entry.rglob("*") if f.is_file()))
                # Get creation time
                created_at = datetime.fromtimestamp(cache_entry.stat().st_ctime, tz=timezone.utc)
                build_cache_info = BuildCacheInfo(path=cache_entry, size_bytes=cache_entry_size, created_at=created_at)

                # Apply CEL filtering
                if compiled_include_filters or compiled_exclude_filters:
                    if not (
                        (
                            not compiled_include_filters
                            or _apply_cel_filters(build_cache_info, compiled_include_filters, [])
                        )
                        and (
                            not compiled_exclude_filters
                            or _apply_cel_filters(build_cache_info, [], compiled_exclude_filters)
                        )
                    ):
                        continue

                if not dry_run:
                    # Remove the cache entry directory
                    shutil.rmtree(cache_entry)

                result.build_cache_destroyed.append(build_cache_info)

            except MngrError as e:
                error_msg = f"Failed to delete cache entry {cache_entry}: {e}"
                result.errors.append(error_msg)
                _handle_error(error_msg, error_behavior, exc=e)


def _get_orphaned_work_dirs(host: OnlineHostInterface, provider_name: ProviderInstanceName) -> list[WorkDirInfo]:
    """Get list of orphaned work directories for a host."""
    certified_data = host.get_certified_data()
    generated_work_dirs = set(certified_data.generated_work_dirs)

    active_work_dirs = set()
    for agent in host.get_agents():
        active_work_dirs.add(str(agent.work_dir))

    orphaned_work_dirs = generated_work_dirs - active_work_dirs

    work_dir_infos = []
    for work_dir_str in orphaned_work_dirs:
        work_dir_path = Path(work_dir_str)
        # Get size if possible
        size = SizeBytes(0)
        try:
            result = host.execute_command(f"du -sb {shlex.quote(str(work_dir_path))} | cut -f1")
            if result.success and result.stdout.strip():
                size = SizeBytes(int(result.stdout.strip()))
        except (ValueError, OSError):
            # If we can't get the size, use 0
            pass

        # Get creation time from the directory
        created_at = datetime.now(timezone.utc)
        try:
            stat_result = host.execute_command(f"stat -c %Y {shlex.quote(str(work_dir_path))}")
            if stat_result.success and stat_result.stdout.strip():
                created_at = datetime.fromtimestamp(int(stat_result.stdout.strip()), tz=timezone.utc)
        except (ValueError, OSError):
            pass

        work_dir_infos.append(
            WorkDirInfo(
                path=work_dir_path,
                size_bytes=size,
                host_id=host.id,
                provider_name=provider_name,
                is_local=host.is_local,
                created_at=created_at,
            )
        )

    return work_dir_infos


def _clean_work_dir(host: OnlineHostInterface, work_dir_path: Path, dry_run: bool) -> None:
    """Clean up a single work directory."""
    if not dry_run:
        with host.lock_cooperatively():
            if _is_git_worktree(host, work_dir_path):
                _remove_git_worktree(host, work_dir_path)
            else:
                _remove_directory(host, work_dir_path)

            _remove_work_dir_from_certified_data(host, work_dir_path)


def _is_git_worktree(host: OnlineHostInterface, path: Path) -> bool:
    """Check if a path is a git worktree.

    A git worktree has a .git file (not directory) that points to the main git directory.
    """
    git_path = path / ".git"

    result = host.execute_command(f"test -f {shlex.quote(str(git_path))}")
    return result.success


def _remove_git_worktree(host: OnlineHostInterface, work_dir_path: Path) -> None:
    """Remove a git worktree using git worktree remove."""
    cmd = f"git worktree remove --force {shlex.quote(str(work_dir_path))}"
    result = host.execute_command(cmd)

    if not result.success:
        logger.warning("git worktree remove failed, falling back to directory removal: {}", result.stderr)
        _remove_directory(host, work_dir_path)
    else:
        logger.debug("Removed git worktree: {}", work_dir_path)


def _remove_work_dir_from_certified_data(host: OnlineHostInterface, work_dir_path: Path) -> None:
    """Remove a work directory from the host's certified data."""
    certified_data = host.get_certified_data()
    existing_dirs = set(certified_data.generated_work_dirs)
    existing_dirs.discard(str(work_dir_path))

    updated_data = certified_data.model_copy_update(
        to_update(certified_data.field_ref().generated_work_dirs, tuple(sorted(existing_dirs))),
    )

    data_json = updated_data.model_dump_json(by_alias=True, indent=2)
    data_path = host.host_dir / "data.json"
    host.write_text_file(data_path, data_json)


def _remove_directory(host: OnlineHostInterface, path: Path) -> None:
    """Remove a directory and all its contents."""
    result = host.execute_command(f"test -e {shlex.quote(str(path))}")
    if result.success:
        cmd = f"rm -rf {shlex.quote(str(path))}"
        result = host.execute_command(cmd)

        if not result.success:
            raise MngrError(f"Failed to remove directory {path}: {result.stderr}")

        logger.debug("Removed directory: {}", path)


def _resource_to_cel_context(resource: Any) -> dict[str, Any]:
    """Convert a resource object to a CEL-friendly dict.

    Supports converting pydantic models (SnapshotInfo, VolumeInfo, WorkDirInfo, LogFileInfo, BuildCacheInfo)
    into a flat dictionary suitable for CEL evaluation.
    """
    if hasattr(resource, "model_dump"):
        result = resource.model_dump(mode="json")

        # Add type field based on the class name
        result["type"] = type(resource).__name__.replace("Info", "").lower()

        # Add computed fields for size
        if "size_bytes" in result and result["size_bytes"] is not None:
            result["size"] = result["size_bytes"]

        # For path-based resources, add name and age from the path
        if "path" in result and isinstance(result["path"], str):
            path = Path(result["path"])
            result["name"] = path.name
            if path.exists():
                stat = path.stat()
                age_seconds = datetime.now(timezone.utc).timestamp() - stat.st_mtime
                result["age"] = age_seconds
            else:
                result["age"] = 0

        # Calculate age from created_at or updated_at
        for date_field in ["created_at", "updated_at"]:
            if date_field in result and result[date_field] is not None:
                if isinstance(result[date_field], str):
                    created_dt = datetime.fromisoformat(result[date_field].replace("Z", "+00:00"))
                else:
                    created_dt = result[date_field]
                result["age"] = (datetime.now(timezone.utc) - created_dt).total_seconds()
                break

        return result

    raise MngrError(f"Cannot convert resource type {type(resource)} to CEL context")


def _apply_cel_filters(
    resource: Any,
    include_filters: Sequence[Any],
    exclude_filters: Sequence[Any],
) -> bool:
    """Apply CEL filters to a resource.

    Returns True if the resource should be included (matches all include filters
    and doesn't match any exclude filters).
    """
    context = _resource_to_cel_context(resource)
    return apply_cel_filters_to_context(
        context=context,
        include_filters=include_filters,
        exclude_filters=exclude_filters,
        error_context_description=str(context),
    )


def _handle_error(error_msg: str, error_behavior: ErrorBehavior, exc: Exception | None = None) -> None:
    """Handle an error according to the specified error behavior."""
    if error_behavior == ErrorBehavior.ABORT:
        if exc:
            raise exc
        raise MngrError(error_msg)
    else:
        # CONTINUE - just log the error
        if exc:
            logger.exception(exc)
        else:
            logger.error(error_msg)
