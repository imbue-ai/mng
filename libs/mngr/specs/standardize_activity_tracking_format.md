# Standardize Activity Tracking Format Spec

This spec documents the current activity tracking formats and proposes options for unification.

## Current State

Activity data is stored in multiple formats across the codebase, making it difficult to write a simple host-side script to calculate "time since last activity."

### Format 1: Agent Activity (JSON)

**Location**: `$MNGR_HOST_DIR/agents/{agent_id}/activity/{activity_type}`

**Written by**: `BaseAgent.record_activity()` (base_agent.py:348-354)

**Format**:
```json
{
  "time": "2024-01-15T10:30:45.123456+00:00"
}
```

**Read by**: `BaseAgent.get_reported_activity_time()` (base_agent.py:339-346) - parses JSON and extracts `time` field.

### Format 2: Host Activity (Plain ISO timestamp, read via mtime)

**Location**: `$MNGR_HOST_DIR/activity/{activity_type}`

**Written by**: `Host.record_activity()` (hosts/host.py:411-418)

**Format**:
```
2024-01-15T10:30:45.123456+00:00
```

**Read by**: `Host.get_reported_activity_time()` (hosts/host.py:406-409) - uses `_get_file_mtime()` and **ignores the file content entirely**.

### Format 3: Process Activity Monitor (JSON, same as Agent)

**Location**: `$MNGR_HOST_DIR/agents/{agent_id}/activity/process`

**Written by**: `Host._start_process_activity_monitor()` (hosts/host.py:1592-1633) - a bash script that runs in the background.

**Format**:
```json
{
  "time": "2024-01-15T10:30:45.123456+00:00"
}
```

**Note**: Uses `date -u +"%Y-%m-%dT%H:%M:%S.%6N+00:00"` with fallback to `date -u +"%Y-%m-%dT%H:%M:%S+00:00"`.

### Format 4: SSH Connect Activity (date command output, read via mtime)

**Location**: `$MNGR_HOST_DIR/activity/ssh`

**Written by**: `_build_activity_wrapper_script()` (cli/create.py:1185-1187)

**Format** (from `date -u +%FT%T%z`):
```
2024-01-15T10:30:45+0000
```

**Note**: The timezone offset lacks the colon (`+0000` vs `+00:00`), making it technically non-ISO-8601-compliant.

**Read by**: File modification time only.

### Format 5: User Activity via Web (marker text, read via mtime)

**Location**: `$MNGR_HOST_DIR/activity/user`

**Written by**: nginx lua block (specs/plugins/user_activity_tracking_via_web.md:79)

**Format**:
```
user_activity
```

**Read by**: File modification time only.

## Summary Table

| Source | Location | Format | Writer | Reader |
|--------|----------|--------|--------|--------|
| Agent activity | `agents/{id}/activity/{type}` | JSON `{"time": "..."}` | Python | JSON parse |
| Host activity | `activity/{type}` | Plain ISO timestamp | Python | **mtime** |
| Process monitor | `agents/{id}/activity/process` | JSON `{"time": "..."}` | Bash | JSON parse |
| SSH connect | `activity/ssh` | `date -u +%FT%T%z` output | Bash | **mtime** |
| Web user activity | `activity/user` | `"user_activity"` marker | Lua/nginx | **mtime** |

## Problems

1. **Inconsistent formats**: JSON vs plain text vs marker text
2. **Inconsistent timestamp formats**: Python `isoformat()` vs `date` command output (timezone offset differs)
3. **Inconsistent reading strategies**: Some parse content, some use mtime
4. **Host-level activity ignores content**: `Host.get_reported_activity_time()` uses mtime, so the timestamp written is wasted
5. **Difficult to script**: A simple shell script on the host would need to handle multiple formats

## Proposed Options

### Option A: Standardize on mtime-only (simplest)

All activity files become "touch files" where only the modification time matters.

**Changes required**:
1. Change `BaseAgent.record_activity()` to just write an empty file or marker
2. Change `BaseAgent.get_reported_activity_time()` to use mtime instead of parsing JSON
3. Change process activity monitor script to just touch the file
4. No changes needed for host activity, SSH, or web activity (already mtime-based)

**Pros**:
- Simplest to implement
- Trivial shell script: `stat -c %Y file` or `stat -f %m file` (macOS)
- No parsing required
- Atomic writes are trivial (just `touch`)

**Cons**:
- Loses the ability to store a precise "reported" timestamp that differs from write time
- If file system timestamps are unreliable (network mounts, clock skew), could be problematic
- Cannot add metadata to activity records in the future

**Shell script example**:
```bash
#!/bin/bash
MNGR_HOST_DIR="${MNGR_HOST_DIR:-$HOME/.mngr}"

latest_mtime=0

# Check all activity files
for f in "$MNGR_HOST_DIR"/activity/* "$MNGR_HOST_DIR"/agents/*/activity/*; do
    if [ -f "$f" ]; then
        mtime=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null)
        if [ "$mtime" -gt "$latest_mtime" ]; then
            latest_mtime=$mtime
        fi
    fi
done

now=$(date +%s)
idle_seconds=$((now - latest_mtime))
echo "$idle_seconds"
```

### Option B: Standardize on JSON format (most expressive)

All activity files use JSON with a `time` field.

**Changes required**:
1. Change `Host.record_activity()` to write JSON (already writes ISO timestamp, just wrap in JSON)
2. Change `Host.get_reported_activity_time()` to parse JSON instead of using mtime
3. Change SSH connect wrapper to write JSON
4. Change web activity plugin to write JSON
5. Update process activity monitor script (already writes JSON, no change needed)

**Pros**:
- Consistent format everywhere
- Extensible - can add metadata fields later (e.g., `source`, `pid`, `details`)
- Explicit timestamp that's not affected by file system issues

**Cons**:
- Harder to write from bash/lua (quoting, escaping)
- Requires JSON parsing in shell scripts
- More complex than mtime approach

**Shell script example** (requires `jq`):
```bash
#!/bin/bash
MNGR_HOST_DIR="${MNGR_HOST_DIR:-$HOME/.mngr}"

latest_time=""

for f in "$MNGR_HOST_DIR"/activity/* "$MNGR_HOST_DIR"/agents/*/activity/*; do
    if [ -f "$f" ]; then
        time=$(jq -r '.time // empty' "$f" 2>/dev/null)
        if [ -n "$time" ] && [[ "$time" > "$latest_time" ]]; then
            latest_time="$time"
        fi
    fi
done

if [ -z "$latest_time" ]; then
    echo "inf"
else
    latest_epoch=$(date -d "$latest_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "$latest_time" +%s 2>/dev/null)
    now=$(date +%s)
    echo $((now - latest_epoch))
fi
```

### Option C: Hybrid - mtime primary, content optional (pragmatic)

Use mtime as the authoritative timestamp, but allow optional content for debugging/auditing.

**Changes required**:
1. Change `BaseAgent.get_reported_activity_time()` to use mtime (like host)
2. Keep writing content as-is for debugging purposes
3. Document that mtime is authoritative

**Pros**:
- Simple shell script (mtime-based)
- Content available for debugging
- Minimal code changes

**Cons**:
- Confusing - two sources of truth
- Content becomes "dead code" that could drift

### Option D: Standardize on plain ISO timestamp (middle ground)

All activity files write a plain ISO 8601 timestamp, and reading always uses mtime.

**Changes required**:
1. Change `BaseAgent.record_activity()` to write plain timestamp instead of JSON
2. Change process activity monitor to write plain timestamp
3. Fix SSH connect to use proper ISO format (`date -Iseconds` or `date -u +%FT%T%z` fixed)
4. Change web activity to write timestamp (or keep marker since mtime is authoritative)
5. Change `BaseAgent.get_reported_activity_time()` to use mtime

**Pros**:
- Simple format that's human-readable
- Easy to write from any language
- Shell script uses mtime (simple)
- Content is still useful for debugging

**Cons**:
- Content and mtime could theoretically disagree (though rare)
- Still need to decide: read content or mtime?

## Recommendation

**Option A (mtime-only)** is recommended for simplicity. The activity tracking system's only purpose is answering "when was the last activity?" - using file modification times is the simplest, most reliable way to do this that works consistently across all writers (Python, Bash, Lua).

If future requirements emerge for storing activity metadata, we can migrate to JSON then. For now, YAGNI applies.

## Implementation Checklist (for Option A)

- [ ] Update `BaseAgent.record_activity()` to write empty/marker content
- [ ] Update `BaseAgent.get_reported_activity_time()` to use mtime via host
- [ ] Update `BaseAgent.get_reported_activity_record()` to document it returns marker content
- [ ] Update process activity monitor bash script to just touch the file
- [ ] Add `get_reported_activity_time()` helper to agent interface that delegates to host mtime check
- [ ] Update specs/idle_detection.md to document the standardized format
- [ ] Add shell script or Python script to calculate idle time from activity files
- [ ] Update tests
