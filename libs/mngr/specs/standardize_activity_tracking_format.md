# Activity Tracking Format Spec

This spec documents the standardized activity tracking format used across the codebase.

## Overview

Activity tracking is used for idle detection - determining when a host or agent was last active. The system needs to answer the question: "How long has it been since activity X occurred?"

## Standardized Format

All activity files follow these conventions:

### File Content: JSON (by convention)

Activity files **should** contain JSON with the following structure:

```json
{
  "time": 1705312245123,
  "...": "additional debugging fields"
}
```

**Required field:**
- `time`: Milliseconds since Unix epoch (January 1, 1970 00:00:00 UTC) as an integer

**Optional debugging fields** (vary by activity type):
- `agent_id`: The agent's ID
- `agent_name`: The agent's name
- `host_id`: The host's ID
- `pane_pid`: The tmux pane PID (for process activity)
- `ssh_pid`: The SSH tracker process PID (for SSH activity)
- `user`: The username (for user activity)

### Reading Activity Time: Always Use mtime

When determining "how long since activity X", **always use the file's modification time (mtime)**, not the JSON content.

This design choice ensures:
1. **Consistency**: All writers (Python, bash, lua) produce the same result
2. **Simplicity**: Simple scripts can just `touch` a file without writing JSON
3. **Robustness**: Works even if JSON is malformed or file is empty

### Writing Activity: JSON Preferred, Touch Acceptable

Writers **should** write JSON for debugging/auditing purposes, but the system will work correctly if they just touch the file (or write any content).

Since writing any content updates the mtime, this is coherent and consistent.

## Activity File Locations

### Host-level activity
- Path: `$MNGR_HOST_DIR/activity/{activity_type}`
- Activity types: `boot`, `user`, `ssh`

### Agent-level activity
- Path: `$MNGR_HOST_DIR/agents/{agent_id}/activity/{activity_type}`
- Activity types: `create`, `start`, `agent`, `process`, `user`

## Activity Types

| Type | Level | Written By | Description |
|------|-------|------------|-------------|
| `create` | Agent | `BaseAgent.record_activity()` | When agent was created |
| `start` | Agent | `BaseAgent.record_activity()` | When agent was started |
| `boot` | Host | `Host.record_activity()` | When host booted |
| `agent` | Agent | Agent itself (self-reporting) | Agent output/thinking |
| `process` | Agent | Process monitor script | Agent process is alive |
| `user` | Host/Agent | `mngr connect`, web plugin | User input activity |
| `ssh` | Host | SSH wrapper script | Active SSH connection |

## Implementation Details

### Python Writers

```python
from datetime import datetime, timezone
import json

def record_activity(path: Path, **extra_fields) -> None:
    """Write activity JSON with timestamp and optional debugging fields."""
    now = datetime.now(timezone.utc)
    data = {
        "time": int(now.timestamp() * 1000),
        **extra_fields,
    }
    path.write_text(json.dumps(data, indent=2))
```

### Bash Writers

```bash
# Write JSON with milliseconds timestamp
TIME_MS=$(($(date +%s) * 1000))
printf '{\n  "time": %d,\n  "pid": %d\n}\n' "$TIME_MS" "$$" > "$ACTIVITY_PATH"
```

### Simple Touch (minimal writer)

```bash
# Just touch the file - mtime will be updated, JSON content not required
touch "$ACTIVITY_PATH"
```

### Reading Activity Time (Python)

```python
def get_activity_time(path: Path) -> datetime | None:
    """Get activity time from file mtime (not JSON content)."""
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except FileNotFoundError:
        return None
```

### Reading Activity Time (Bash)

```bash
# Get mtime as Unix timestamp (Linux)
stat -c %Y "$ACTIVITY_PATH"

# Get mtime as Unix timestamp (macOS)
stat -f %m "$ACTIVITY_PATH"

# Cross-platform
stat -c %Y "$ACTIVITY_PATH" 2>/dev/null || stat -f %m "$ACTIVITY_PATH" 2>/dev/null
```

## Example: Calculate Idle Time

```bash
#!/bin/bash
# Calculate seconds since last activity across all activity files

MNGR_HOST_DIR="${MNGR_HOST_DIR:-$HOME/.mngr}"
latest_mtime=0

# Check all activity files (host-level and agent-level)
for f in "$MNGR_HOST_DIR"/activity/* "$MNGR_HOST_DIR"/agents/*/activity/*; do
    if [ -f "$f" ]; then
        mtime=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null)
        if [ "$mtime" -gt "$latest_mtime" ]; then
            latest_mtime=$mtime
        fi
    fi
done

if [ "$latest_mtime" -eq 0 ]; then
    echo "inf"
else
    now=$(date +%s)
    echo $((now - latest_mtime))
fi
```

## Web Activity Plugin

The `user_activity_tracking_via_web` plugin should write JSON when reporting user activity:

```lua
-- nginx lua block
local time_ms = math.floor(ngx.now() * 1000)
local json = string.format('{\n  "time": %d,\n  "source": "web"\n}\n', time_ms)
local f = io.open(os.getenv("MNGR_HOST_DIR") .. "/activity/user", "w")
f:write(json)
f:close()
```

Or simply touch the file (mtime is authoritative):

```lua
os.execute("touch " .. os.getenv("MNGR_HOST_DIR") .. "/activity/user")
```

## Rationale

This design balances several concerns:

1. **Simplicity**: Using mtime means any write updates the activity time, even a simple `touch`
2. **Debuggability**: JSON content provides useful metadata for troubleshooting
3. **Consistency**: All writers and readers behave the same way
4. **Cross-language**: Works with Python, bash, lua, or any other language
5. **Robustness**: Even if JSON is malformed, the mtime-based reading still works
