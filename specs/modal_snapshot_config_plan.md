# Plan: Modal Provider Snapshot Configuration

## Overview

Add configuration option to control whether an initial snapshot is created when a Modal host is created, and automatically snapshot hosts when they are stopped.

## Current State

- `create_host` always calls `_create_initial_snapshot` after host setup (lines 997-1000)
- `stop_host` accepts `create_snapshot` parameter but doesn't use it for snapshotting
- Every host currently has at least one snapshot (the "initial" snapshot)

## Changes Required

### 1. Add Config Option to ModalProviderConfig

**File**: `libs/mngr/imbue/mngr/providers/modal/config.py`

Add field:
```python
is_snapshotted_after_create: bool = Field(
    default=True,
    description=(
        "Whether to create an initial snapshot immediately after host creation. "
        "When True (default), an 'initial' snapshot is created, allowing the host "
        "to be restarted even if it's hard-killed. When False, the host can only "
        "be restarted if it was stopped gracefully (which creates a snapshot)."
    ),
)
```

### 2. Modify create_host to Conditionally Create Initial Snapshot

**File**: `libs/mngr/imbue/mngr/providers/modal/instance.py`
**Method**: `create_host` (around line 997-1000)

Change from:
```python
# Create an initial snapshot so the host can always be restarted after being stopped
logger.debug("Creating initial snapshot for host", host_id=str(host_id))
self._create_initial_snapshot(sandbox, host_id)
```

To:
```python
# Optionally create an initial snapshot based on config
if self.config.is_snapshotted_after_create:
    logger.debug("Creating initial snapshot for host", host_id=str(host_id))
    self._create_initial_snapshot(sandbox, host_id)
```

### 3. Modify stop_host to Create Snapshot Before Termination

**File**: `libs/mngr/imbue/mngr/providers/modal/instance.py`
**Method**: `stop_host` (lines 1005-1032)

Before terminating the sandbox, if `create_snapshot=True` and sandbox is running, create a snapshot.

Modified flow:
1. Find the sandbox
2. If sandbox exists and `create_snapshot=True`:
   - Create a snapshot using `self.create_snapshot(host_id, SnapshotName("stop"))`
3. Terminate the sandbox
4. Update cache

### 4. Test Scenarios

**File**: `libs/mngr/imbue/mngr/providers/modal/instance_test.py`

#### Test 1: `is_snapshotted_after_create=True` + Hard Kill

Test that when initial snapshot is enabled, a host can be restarted even after the sandbox is terminated directly (simulating a hard kill).

```python
def test_restart_after_hard_kill_with_initial_snapshot(
    modal_provider: ModalProviderInstance,
    unique_host_name: HostName,
) -> None:
    """Host can restart after hard kill when initial snapshot is enabled."""
    # Create host (config defaults to is_snapshotted_after_create=True)
    host = modal_provider.create_host(unique_host_name)
    host_id = host.id

    # Hard kill: directly terminate without using stop_host
    sandbox = modal_provider._find_sandbox_by_host_id(host_id)
    sandbox.terminate()
    modal_provider._uncache_sandbox(host_id, unique_host_name)

    # Should be able to restart using the initial snapshot
    restarted = modal_provider.start_host(host_id)
    assert restarted is not None
```

#### Test 2: `is_snapshotted_after_create=False` + Normal Stop

Test that when initial snapshot is disabled, a graceful stop creates a snapshot, allowing restart.

```python
def test_restart_after_graceful_stop_without_initial_snapshot(
    modal_provider_factory: Callable[..., ModalProviderInstance],
    unique_host_name: HostName,
) -> None:
    """Host can restart after graceful stop even without initial snapshot."""
    # Create provider with is_snapshotted_after_create=False
    provider = modal_provider_factory(is_snapshotted_after_create=False)

    # Create host - should have NO initial snapshot
    host = provider.create_host(unique_host_name)
    host_id = host.id

    snapshots = provider.list_snapshots(host_id)
    assert len(snapshots) == 0  # No initial snapshot

    # Graceful stop - should create a snapshot
    provider.stop_host(host_id, create_snapshot=True)

    # Verify snapshot was created
    snapshots = provider.list_snapshots(host_id)
    assert len(snapshots) == 1

    # Should be able to restart
    restarted = provider.start_host(host_id)
    assert restarted is not None
```

#### Test 3: `is_snapshotted_after_create=False` + Hard Kill

Test that when initial snapshot is disabled and sandbox is hard-killed, restart fails.

```python
def test_restart_fails_after_hard_kill_without_initial_snapshot(
    modal_provider_factory: Callable[..., ModalProviderInstance],
    unique_host_name: HostName,
) -> None:
    """Host cannot restart after hard kill when no initial snapshot exists."""
    # Create provider with is_snapshotted_after_create=False
    provider = modal_provider_factory(is_snapshotted_after_create=False)

    # Create host - should have NO initial snapshot
    host = provider.create_host(unique_host_name)
    host_id = host.id

    # Hard kill: directly terminate without using stop_host
    sandbox = provider._find_sandbox_by_host_id(host_id)
    sandbox.terminate()
    provider._uncache_sandbox(host_id, unique_host_name)

    # Should fail to restart because no snapshots exist
    with pytest.raises(NoSnapshotsModalMngrError):
        provider.start_host(host_id)
```

## Implementation Order

1. Add `is_snapshotted_after_create` config option
2. Modify `create_host` to conditionally create initial snapshot
3. Modify `stop_host` to create snapshot before termination
4. Update existing tests that expect initial snapshot (may need adjustment for count expectations)
5. Add new test scenarios
6. Run all tests and fix any issues

## Notes

- The `stop_host` method already has a `create_snapshot` parameter that defaults to `True`, so we just need to implement the actual snapshotting behavior
- Need to handle the case where sandbox is already terminated when `stop_host` is called (can't create snapshot in that case)
- Should use a descriptive snapshot name like "stop" for snapshots created during stop
