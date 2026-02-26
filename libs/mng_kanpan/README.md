# Kanpan

All-seeing agent tracker. The name combines Sino-Japanese 看 (*kan*, "to look", as in 看板 *kanban*) and Greek πᾶν (*pan*, "all") -- a unified view that aggregates state from all sources (mng agent lifecycle, git branches, GitHub PRs and CI) into a single board.

## Usage

```
mng kanpan
```

Launches a terminal UI that displays all mng agents organized by their PR lifecycle:

- **Done** -- PR merged
- **Cancelled** -- PR closed
- **In review** -- PR pending (includes drafts)
- **In progress** -- no PR yet
- **Muted** -- manually silenced, shown at the bottom in gray

Each agent shows its lifecycle state, push status, CI check results, and a link to its PR (or a link to create one).

## Keybindings

| Key | Action |
|-----|--------|
| r | Refresh the board |
| p | Push the focused agent's branch to remote |
| d | Delete the focused agent (confirms if PR not merged) |
| m | Mute/unmute the focused agent |
| q | Quit |

Custom commands can be added via config (see below).

## Configuration

Add to your mng settings file (e.g. `.mng/settings.toml`):

```toml
[plugins.kanpan.commands.c]
name = "connect"
command = "mng connect $MNG_AGENT_NAME"

[plugins.kanpan.commands.l]
name = "logs"
command = "mng logs $MNG_AGENT_NAME"
refresh_afterwards = true
```

Each custom command gets a keybinding (the table key, e.g. `c`), appears in the status bar, and runs with the `MNG_AGENT_NAME` environment variable set to the focused agent's name.

Fields:

- `name` -- display name shown in the status bar
- `command` -- shell command to run
- `refresh_afterwards` -- whether to refresh the board after the command completes (default: false)

## Requirements

- `gh` CLI installed and authenticated (for GitHub PR information)
- mng configured with at least one provider
