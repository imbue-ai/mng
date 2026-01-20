# Process Cleanup for tmux Sessions

## Problem Statement

Agents run in tmux sessions locally. When stopping an agent, we need to ensure **all** processes spawned from that tmux session are cleaned up. This is tricky because:

1. Users can create new windows/panes in tmux, each with its own shell
2. Each new shell becomes its own session leader (new SID)
3. There isn't a single SID covering the whole tmux session

The question: Is tracking SIDs valuable, or should we focus on PIDs and process groups?

## Current Implementation

Located in `hosts/host.py:1131-1210`, `stop_agents()`:

1. Gets all pane PIDs via `tmux list-panes -t session -F '#{pane_pid}'`
2. Recursively gets descendant PIDs via `pgrep -P $pid`
3. Gets process group IDs (PGID) for pane PIDs
4. Sends SIGTERM to process groups (`kill -TERM -- -$pgid`)
5. Sends SIGTERM/SIGKILL to individual PIDs
6. Kills the tmux session

## Understanding SIDs, PGIDs, and PIDs

### Session ID (SID)
- Groups processes sharing a controlling terminal
- Created when a process calls `setsid()`
- Each tmux pane's shell is already a session leader with its own SID
- `pkill -s $sid` kills all processes in a session

### Process Group ID (PGID)
- Groups related processes (job control)
- `kill -- -$pgid` sends signal to entire group

### Key Insight
**Each tmux pane's shell is already a session leader.** When a user creates a new window (Ctrl-b c) or splits a pane, tmux spawns a new shell that becomes its own session leader. So there are as many SIDs as there are panes - no single SID covers the whole tmux session.

## What the Current Approach Handles

| Scenario | Handled? | Why |
|----------|----------|-----|
| New tmux window | Yes | Listed by `tmux list-panes` |
| Split pane | Yes | Listed by `tmux list-panes` |
| Background job (`&`) | Yes | Child of pane shell, found by `pgrep -P` |
| `nohup` process | Yes | Still a descendant |
| `setsid` in user script | Yes | Still a descendant of shell |
| **Daemonized process** | **NO** | Detaches from tree, reparented to init |

## The Real Gap

The **only** case that escapes both PID tracking and SID tracking is **daemonization** - where a process double-forks and detaches completely. Such processes:

1. Are not descendants of any pane shell
2. Have their own SID (called `setsid()` during daemonization)
3. Are reparented to PID 1

**SID tracking via tmux hooks would NOT help here** because the daemonized process creates its own SID.

## Options

### Option 1: Add SID-Based Cleanup (Marginal Improvement)

Use tmux hooks to track SIDs:

```bash
# In tmux.conf, after creating a pane, record its shell's SID
set-hook -g after-new-session 'run-shell "echo $$ >> $MNGR_AGENT_STATE_DIR/sids"'
set-hook -g after-new-window 'run-shell "echo $$ >> $MNGR_AGENT_STATE_DIR/sids"'
set-hook -g after-split-window 'run-shell "echo $$ >> $MNGR_AGENT_STATE_DIR/sids"'
```

On cleanup:
```bash
for sid in $(cat $MNGR_AGENT_STATE_DIR/sids); do
    pkill -s $sid 2>/dev/null || true
done
```

**Pros:**
- Simple to implement
- Works within existing tmux config infrastructure
- Catches processes whose parent died but didn't daemonize

**Cons:**
- Still doesn't catch daemonized processes
- Marginal improvement over current PGID-based approach
- SID file could get out of sync if tmux crashes

**Verdict:** Marginal value.

### Option 2: Linux cgroups (Most Robust)

Create a cgroup for each agent. All processes (including daemonized ones) stay in the cgroup.

```python
def start_agents(self, agent_ids: Sequence[AgentId]) -> None:
    for agent_id in agent_ids:
        cgroup_path = f"/sys/fs/cgroup/mngr/{agent_id}"
        os.makedirs(cgroup_path, exist_ok=True)
        # Write current process to cgroup, then spawn tmux
        Path(f"{cgroup_path}/cgroup.procs").write_text(str(os.getpid()))
        # tmux and all its children inherit the cgroup
        subprocess.run(["tmux", "new-session", ...])

def stop_agents(self, agent_ids: Sequence[AgentId]) -> None:
    for agent_id in agent_ids:
        cgroup_path = f"/sys/fs/cgroup/mngr/{agent_id}"
        # Read all PIDs in cgroup and kill them
        pids = Path(f"{cgroup_path}/cgroup.procs").read_text().split()
        for pid in pids:
            os.kill(int(pid), signal.SIGKILL)
```

**Pros:**
- **Catches everything** - including daemonized processes
- No process can escape
- Kernel-maintained, very reliable
- Industry standard (used by systemd, Docker, etc.)

**Cons:**
- Linux-only
- Requires cgroup v2 setup
- May need root for initial cgroup creation
- More complex implementation

**Verdict:** Proper solution for guaranteed cleanup. Consider for "hardened" mode.

### Option 3: Environment Variable Tracking via /proc

Set `MNGR_AGENT_ID` (already done!) and scan `/proc` for processes with it:

```python
def _find_processes_with_env(self, agent_id: str) -> list[int]:
    pids = []
    for pid_dir in Path("/proc").iterdir():
        if pid_dir.name.isdigit():
            try:
                environ = (pid_dir / "environ").read_bytes()
                if f"MNGR_AGENT_ID={agent_id}".encode() in environ:
                    pids.append(int(pid_dir.name))
            except (PermissionError, FileNotFoundError):
                pass
    return pids
```

**Pros:**
- Catches daemonized processes that inherited the env var
- Already have `MNGR_AGENT_ID` set
- Works on macOS too (via different mechanism)

**Cons:**
- Slow (scanning all /proc entries)
- Processes that clear their environment would escape
- Permission issues with some processes

**Verdict:** Good fallback/safety net, not primary mechanism.

### Option 4: Enhanced Current Approach (Recommended)

Keep current PID/PGID tracking, add layers:

```python
def stop_agents(self, agent_ids: Sequence[AgentId], timeout_seconds: float = 5.0) -> None:
    for agent_id in agent_ids:
        # 1. Get pane PIDs and their SIDs
        pane_pids = self._get_pane_pids(session_name)

        # 2. Kill by SID (catches non-daemonized processes)
        for pane_pid in pane_pids:
            sid = self._get_sid(pane_pid)
            self.execute_command(f"pkill -s {sid} 2>/dev/null || true")

        # 3. Kill descendants by PID tree (current approach)
        all_pids = self._get_all_descendant_pids(pane_pids)
        # ... existing SIGTERM/SIGKILL logic ...

        # 4. Final sweep: find stragglers by MNGR_AGENT_ID in /proc
        stragglers = self._find_processes_with_mngr_agent_id(agent_id)
        for pid in stragglers:
            os.kill(pid, signal.SIGKILL)

        # 5. Kill tmux session
        self.execute_command(f"tmux kill-session -t '{session_name}'")
```

**Pros:**
- Defense-in-depth with multiple approaches
- No special privileges or cgroup setup needed
- Cross-platform (with platform-specific env scanning)
- Catches most realistic scenarios

**Cons:**
- More code
- Not 100% if process clears env and daemonizes

**Verdict:** Best balance of robustness and practicality.

## Conclusions

### Does SID tracking help?

**Not significantly.** The current PID/descendant approach already handles the main cases. The only gap is daemonized processes, which SID tracking also cannot solve.

SID would help if:
- A process's parent died but the process didn't daemonize
- You wanted to kill an entire session with one `pkill -s` call

But both are already handled by PGID + descendant tracking.

### Recommendation

**Option 4 (Enhanced Current Approach):**

1. Keep current PID/PGID logic (handles 95% of cases)
2. Add `pkill -s $sid` for each pane's SID as extra layer
3. Add final `/proc` sweep for `MNGR_AGENT_ID` to catch stragglers
4. Document that truly daemonized processes may escape

If guaranteed cleanup is needed later (e.g., untrusted agents), implement Option 2 (cgroups) as a separate "hardened" provider mode.
