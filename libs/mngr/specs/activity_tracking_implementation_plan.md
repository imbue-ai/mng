# Activity Tracking Implementation Plan

This plan covers ensuring that CREATE and BOOT activity files are populated correctly when hosts are created and started.

## Current State

### Infrastructure exists but is not used

The activity tracking infrastructure exists:

- `Host.record_activity(activity_type)` at `hosts/host.py:407-416` - writes an ISO timestamp to `$MNGR_HOST_DIR/activity/<type>`
- `Host.get_reported_activity_time(activity_type)` - reads the file mtime
- `ActivitySource` enum has `CREATE`, `BOOT`, and other types

**Problem**: Neither `create_host()` nor `start_host()` in any provider implementation calls `record_activity()`. The activity files are never created.

## What needs to happen

| Event | Activity to record |
|-------|-------------------|
| `provider.create_host()` returns | `CREATE` and `BOOT` (host is created AND started) |
| `provider.start_host()` returns | `BOOT` (host is starting after being stopped) |

## Implementation Options

### Option A: Record in each provider implementation

Add calls to `record_activity()` at the end of each provider's `create_host()` and `start_host()` methods.

**Providers to modify:**
- `providers/local/instance.py` - `create_host()`, `start_host()`
- `providers/modal/instance.py` - `create_host()`, `start_host()`
- `providers/ssh/instance.py` - `create_host()`, `start_host()`

**Pros:** Simple, explicit
**Cons:** Easy to forget in new providers, duplicates code

### Option B: Record in BaseProviderInstance using template method pattern

Refactor `BaseProviderInstance` to have concrete `create_host()` and `start_host()` methods that:
1. Call an abstract `_do_create_host()` / `_do_start_host()` method
2. Record the appropriate activity
3. Return the host

```python
def create_host(self, ...) -> Host:
    host = self._do_create_host(...)
    host.record_activity(ActivitySource.CREATE)
    host.record_activity(ActivitySource.BOOT)
    return host

def start_host(self, ...) -> Host:
    host = self._do_start_host(...)
    host.record_activity(ActivitySource.BOOT)
    return host
```

**Pros:** Guaranteed to happen for all providers, no code duplication
**Cons:** Requires refactoring all providers to use new method names

### Option C: Record at the API layer

Add recording in `api/create.py` after `resolve_target_host()` returns, and in an `api/start.py` (if it exists) or wherever `start_host` is called from.

**Pros:** Centralized
**Cons:** If someone calls provider methods directly, activity won't be recorded

## Recommendation

**Option A** is simplest for now. We can add 4 lines of code to each provider:
- 2 lines in `create_host()`: `host.record_activity(ActivitySource.CREATE)` and `host.record_activity(ActivitySource.BOOT)`
- 1 line in `start_host()`: `host.record_activity(ActivitySource.BOOT)`

This can be done quickly and tested immediately. If we add more providers later, we can refactor to Option B.

## Files to modify

1. `libs/mngr/imbue/mngr/providers/local/instance.py`
   - `create_host()`: Add `host.record_activity(ActivitySource.CREATE)` and `host.record_activity(ActivitySource.BOOT)` before return
   - `start_host()`: Add `host.record_activity(ActivitySource.BOOT)` before return

2. `libs/mngr/imbue/mngr/providers/modal/instance.py`
   - `create_host()`: Same as above
   - `start_host()`: Same as above

3. `libs/mngr/imbue/mngr/providers/ssh/instance.py`
   - `create_host()`: Same as above
   - `start_host()`: Same as above

## Testing

The activity files should appear at `$MNGR_HOST_DIR/activity/create` and `$MNGR_HOST_DIR/activity/boot` after:
1. Creating a new host
2. Starting a stopped host

Existing unit tests in `hosts/test_host.py` already test the `record_activity` method itself. We may want to add integration tests that verify the full flow.
