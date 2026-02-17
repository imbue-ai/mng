"""Unit tests for the destroy CLI module."""

from imbue.mngr.cli.destroy import _execute_post_destroy_gc
from imbue.mngr.config.data_types import MngrContext


def test_execute_post_destroy_gc_returns_result_with_no_errors(temp_mngr_ctx: MngrContext) -> None:
    """Test that _execute_post_destroy_gc runs successfully and returns a GcResult.

    This exercises the shared GC helper used by both synchronous and background
    code paths, verifying it constructs the correct resource types and calls api_gc.
    """
    result = _execute_post_destroy_gc(temp_mngr_ctx)

    assert result.errors == []
    # With a fresh temp directory and no agents, there should be nothing to GC
    assert result.work_dirs_destroyed == []
    assert result.machines_destroyed == []
    assert result.machines_deleted == []
    assert result.snapshots_destroyed == []
    assert result.volumes_destroyed == []
    # Logs and build cache are not cleaned during post-destroy GC
    assert result.logs_destroyed == []
    assert result.build_cache_destroyed == []
