# Activity Tracking Implementation Plan

This plan covers ensuring that activity files are populated correctly for idle detection to work.

## Background

From `docs/concepts/idle_detection.md`, the following activity types can count towards keeping a host alive:

| Activity | Description | Level | Trustworthy? |
|----------|-------------|-------|--------------|
| BOOT | Host came online | Host | Yes |
| CREATE | Agent was created | Agent | Yes |
| START | Agent was started | Agent | No |
| PROCESS | Agent process is alive | Agent | No |
| SSH | Active SSH connection | Host | No |
| AGENT | Agent output activity | Agent | No (self-reported) |
| USER | User input (keystrokes/mouse) | Host | No (self-reported) |

**This plan covers: BOOT, CREATE, START, PROCESS, and SSH.**

AGENT and USER are out of scope - AGENT is self-reported by agents, and USER requires the web plugin or `mngr connect` keystroke tracking (separate work).

## Activity File Locations

- **Host-level**: `$MNGR_HOST_DIR/activity/<type>` (e.g., `activity/boot`, `activity/ssh`)
- **Agent-level**: `$MNGR_HOST_DIR/agents/<agent_id>/activity/<type>` (e.g., `agents/agent-xxx/activity/create`)

## Current State

The infrastructure exists but is not being used:
- `Host.record_activity()` - exists at `hosts/host.py:407`, writes to host-level activity files
- `BaseAgent.record_activity()` - exists at `agents/base_agent.py:348`, writes to agent-level activity files
- `Host.get_idle_seconds()` - exists at `hosts/host.py:1701`, reads host-level activity files

**Problem**: Nothing actually calls these `record_activity()` methods during normal operations.

## Implementation Plan

### 1. BOOT Activity (Host-level)

**When**: Record when a host boots/comes online.

**Where to add calls**:
- `providers/local/instance.py` - in `create_host()` and `start_host()`
- `providers/modal/instance.py` - in `create_host()` and `start_host()`
- `providers/ssh/instance.py` - in `create_host()` and `start_host()`

**Implementation**:
```python
# At end of create_host() and start_host():
host.record_activity(ActivitySource.BOOT)
return host
```

### 2. CREATE Activity (Agent-level)

**When**: Record when an agent is created.

**Where to add call**:
- `hosts/host.py` - in `create_agent_state()` at line ~1146, after agent is created but before return

**Implementation**:
```python
# At end of create_agent_state(), before return:
agent.record_activity(ActivitySource.CREATE)
return agent
```

### 3. START Activity (Agent-level)

**When**: Record when an agent is started.

**Where to add call**:
- `hosts/host.py` - in `start_agents()` at line ~1457, after each agent's tmux session is created

**Implementation**:
```python
# Inside the for loop, after tmux session is successfully created:
agent.record_activity(ActivitySource.START)
```

### 4. PROCESS Activity (Agent-level)

**When**: Continuously update while the agent process is alive.

**Approach**: Start a background monitor when the agent starts that periodically writes to the PROCESS activity file as long as the agent process exists.

**Options**:

**Option A: Background shell script in tmux**
- When starting the agent in `start_agents()`, also start a monitoring script in the background
- Script polls for tmux session existence and writes to activity file
- Script exits when tmux session dies

```bash
# Monitor script (run in background)
while tmux has-session -t "$SESSION_NAME" 2>/dev/null; do
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ACTIVITY_FILE"
    sleep 30
done
```

**Option B: Wrapper script around agent command**
- Wrap the agent command in a script that writes activity periodically
- More reliable but more complex

**Recommendation**: Option A is simpler. Create a small monitoring script that runs alongside the agent.

### 5. SSH Activity (Host-level)

**When**: Update while an SSH connection is active (i.e., during `mngr connect`).

**Current state**: `mngr connect` currently does `os.execvp("tmux", ...)` which replaces the process. This makes it hard to track activity from the client side.

**Approach**: Track SSH activity from within the host, not the client.

**Options**:

**Option A: Monitor active tmux client connections**
- A host-side script that checks if any tmux sessions have attached clients
- Writes to `$MNGR_HOST_DIR/activity/ssh` when clients are attached

**Option B: Wrapper around tmux attach**
- Instead of `os.execvp`, use a subprocess that monitors the connection
- Periodically touches the SSH activity file while connected

**Option C: Use tmux hooks**
- tmux has `client-attached` and `client-detached` hooks
- Configure these to update the activity file

**Recommendation**: Option C (tmux hooks) is cleanest. Add hooks in the host tmux config that update the SSH activity file.

```
# In tmux config
set-hook -g client-attached 'run-shell "echo $(date -u +%Y-%m-%dT%H:%M:%SZ) > $MNGR_HOST_DIR/activity/ssh"'
```

## Summary of Changes

| File | Change |
|------|--------|
| `providers/local/instance.py` | Add `host.record_activity(BOOT)` in `create_host()` and `start_host()` |
| `providers/modal/instance.py` | Add `host.record_activity(BOOT)` in `create_host()` and `start_host()` |
| `providers/ssh/instance.py` | Add `host.record_activity(BOOT)` in `create_host()` and `start_host()` |
| `hosts/host.py` | Add `agent.record_activity(CREATE)` in `create_agent_state()` |
| `hosts/host.py` | Add `agent.record_activity(START)` in `start_agents()` |
| `hosts/host.py` | Start PROCESS monitor script in `start_agents()` |
| `hosts/host.py` | Add SSH activity hooks in `_create_host_tmux_config()` |

## Open Questions

1. **PROCESS monitor polling interval**: 30 seconds? Configurable?

2. **Host.record_activity() currently accepts CREATE**: This seems wrong since CREATE should be agent-level. Should we remove CREATE from the allowed types in `Host.record_activity()`?

3. **Host.get_idle_seconds() only checks host-level files**: It doesn't check agent-level activity files. Should it iterate through all agents and check their activity files too? Or should agent activities also write to host-level files?

4. **SSH activity for remote hosts**: The tmux hook approach works for local hosts. For remote hosts accessed via actual SSH, we might need a different mechanism (e.g., checking `who` or `ss` for active SSH connections).

## Testing

After implementation, verify:
1. `$MNGR_HOST_DIR/activity/boot` exists after `mngr create`
2. `$MNGR_HOST_DIR/agents/<id>/activity/create` exists after agent creation
3. `$MNGR_HOST_DIR/agents/<id>/activity/start` exists after agent start
4. `$MNGR_HOST_DIR/agents/<id>/activity/process` is updated periodically while agent runs
5. `$MNGR_HOST_DIR/activity/ssh` is updated when attached to tmux session
