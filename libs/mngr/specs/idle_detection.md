When relevant, the last user input time is tracked via:
- Keystrokes sent when running `mngr connect` (terminal) [future]
- Mouse/keyboard events via injected JS [future] (when accessing an agent via the web with default plugins that run `ttyd` and configure `nginx` to inject the script)

When relevant, the last agent output time is tracked by writing to an activity file (self-reporting, configured by default for most agents). See [agent conventions](./conventions.md#Activity-Reporting) for details.

Automatic host stopping based on idle timeout [future], SSH connection tracking [future], and agent process monitoring (`ActivitySource.PROCESS`) [future] are also planned.

## Activity File Format

Activity is recorded by writing JSON to a file. The file's **modification time (mtime)** is the authoritative timestamp for determining "time since last activity."

See [standardize_activity_tracking_format.md](./standardize_activity_tracking_format.md) for the full specification.

### JSON Format (by convention)

```json
{
  "time": 1705312245123,
  "agent_id": "abc123",
  "...": "other debugging fields"
}
```

- `time`: Milliseconds since Unix epoch (int)
- Additional fields vary by activity type and are for debugging only

### Reading Activity Time

Always use file mtime, not JSON content. This allows simple scripts to just `touch` files.

```bash
# Calculate idle time
stat -c %Y "$MNGR_HOST_DIR/activity/user" 2>/dev/null || stat -f %m "$MNGR_HOST_DIR/activity/user"
```

### Activity File Locations

- Host-level: `$MNGR_HOST_DIR/activity/{type}` (boot, user, ssh)
- Agent-level: `$MNGR_HOST_DIR/agents/{id}/activity/{type}` (create, start, agent, process)

Note: The following features are planned but not yet documented: `mngr limit` command for configuring idle detection, `mngr enforce` command for checking and enforcing idle timeouts, `mngr open` command for opening agent URLs with activity tracking, and applying `--idle-mode`, `--idle-timeout`, and `--activity-sources` flags from `mngr create`.
