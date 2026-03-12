# Kanpan

All-seeing agent tracker. The name combines Sino-Japanese 看 (*kan*, "to look", as in 看板 *kanban*) and Greek πᾶν (*pan*, "all") -- a unified view that aggregates state from all sources (mng agent lifecycle, git branches, GitHub PRs and CI) into a single board.

Launch with `mng kanpan`. Requires the `gh` CLI to be installed and authenticated.

## Filtering

Filter which agents appear on the board using CEL expressions:

```bash
# Show only agents for a specific project
mng kanpan --project mng

# Show only running agents
mng kanpan --include 'state == "RUNNING"'

# Exclude done agents
mng kanpan --exclude 'state == "DONE"'
```

`--include` and `--exclude` accept arbitrary CEL expressions (repeatable). `--project` is a convenience shorthand that translates to an include filter on `labels.project`. Multiple `--project` flags are OR'd together.

When any filter is active, the header displays a `[filtered]` indicator.

## Custom commands

Add to your mng settings file (e.g. `.mng/settings.toml`):

```toml
[plugins.kanpan.commands.c]
name = "connect"
command = "mng connect $MNG_AGENT_NAME"

[plugins.kanpan.commands.l]
name = "events"
command = "mng events $MNG_AGENT_NAME"
refresh_afterwards = true
```

Each entry defines a keybinding (the table key, e.g. `c`) that appears in the status bar and runs with the `MNG_AGENT_NAME` environment variable set to the focused agent's name. Custom commands override builtins when they share the same key. Set `enabled = false` to disable a builtin.

By default, custom commands run immediately on the focused agent. Set `markable = true` to make a command use dired-style batch marking instead: pressing the key marks agents, then `x` executes all marks at once.

```toml
[plugins.kanpan.commands.s]
name = "stop"
command = "mng stop $MNG_AGENT_NAME"
markable = true
refresh_afterwards = true
```

## Custom columns

Add extra columns to the board that display per-agent data. Each column reads from one of two sources:

- **Labels** (default) -- reads `agent.labels[key]`, where `key` is the column's config key.
- **Plugin state** (default for plugin columns) -- reads from certified data in `data.json` (written by `set_plugin_data()`) and reported plugin state files at `$STATE_DIR/plugin/<plugin_name>/<field>` (written by `set_reported_plugin_file()`). State files take precedence when both exist.
- **Plugin agent data** -- reads from `AgentDetails.plugin`, populated by `agent_field_generators`. Set `source = "agent"` to use this source.

Values can be colored by mapping specific strings to urwid color names.

```toml
# Label-backed column: shows agent.labels["blocked"]
[plugins.kanpan.columns.blocked]
header = "BLOCKED"
[plugins.kanpan.columns.blocked.colors]
unblocked = "light green"
blocked = "light red"

# Plugin-data-backed column: shows plugin data for claude/waiting_reason
[plugins.kanpan.columns.waiting]
header = "WAIT"
plugin_name = "claude"
field = "waiting_reason"
[plugins.kanpan.columns.waiting.colors]
PERMISSIONS = "light red"
END_OF_TURN = "light green"
```

By default, custom columns appear after the built-in columns (before LINK). To control the order of all columns, set `column_order`:

```toml
[plugins.kanpan]
column_order = ["name", "state", "custom_blocked", "git", "pr", "ci", "link"]
```

Built-in column names are: `name`, `state`, `git`, `pr`, `ci`, `link`. Custom columns use `custom_<key>` (e.g. `custom_blocked` for a column defined under `[plugins.kanpan.columns.blocked]`). Columns not listed in `column_order` are omitted.

When no label or plugin data is present for an agent, the column shows an empty cell.

## Refresh behavior

Kanpan uses two refresh strategies:

- **Full refresh** (manual 'r' key, periodic 10-minute timer): fetches both agent state and GitHub PR data. Only one can be in flight at a time -- pressing 'r' while a refresh is running is ignored.
- **Agent-only refresh** (after push, delete, custom commands): fetches agent state without hitting the GitHub API. PR data is carried forward from the previous snapshot.

Both are configurable:

```toml
[plugins.kanpan]
# Seconds between periodic full refreshes (default 10 minutes)
refresh_interval_seconds = 600.0
# Seconds before retrying after a failed full refresh
retry_cooldown_seconds = 60.0
```
