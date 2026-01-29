# mngr pair [future] - CLI Options Reference

Continuously syncs files between a source (some agent or host) and a target (another agent or host)

By default, syncs between an agent and your local directory.

This is the equivalent of "pairing mode"--changes are watched and synced in real-time as they occur.

This command is "git-aware", but git is not required (if you just have two directories, it will sync files between them).

## Usage

```
mngr pair [(--agent) agent [--target-agent other-agent]]
```

## General

- `--source SOURCE`: Directory to use as work_dir root. Accepts a unified syntax: `[AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]` [default: if a pty and this arg is omitted, presents a TUI for selecting the agent, otherwise errors unless defined]
- `--source-agent AGENT`: Source agent
- `--source-host HOST`: Source host
- `--source-path PATH`: Source path
- `--target TARGET`: Target. Accepts a unified syntax: `[HOST]:PATH` [default: nearest parent directory with a .git folder, starting from the current directory]
- `--target-agent TARGET`: Target agent.
- `--target-host HOST`: Target host.
- `--target-path PATH`: Directory to mount source inside agent host.
- `--list`: List active pairs and exit

## File Filtering

- `--include-gitignored`: Include files that match `.gitignore` patterns
- `--include PATTERN`: Include files matching glob pattern [repeatable]
- `--exclude PATTERN`: Exclude files matching glob pattern [repeatable]
- `--include-file FILE`: Read include patterns from file (one per line)
- `--exclude-file FILE`: Read exclude patterns from file (one per line)

## Git Handling

- `--[no-]require-git`: Require that both source and target are git repositories [default: require git]
- `--abort-on-branch-change / --follow-branch-change`: Either abort syncing if a git change is detected, or switch to that branch [default: follow]
- `--[no-]auto-stash`: Automatically stash local git state before starting, and re-apply it after [default: auto-stash]
- `--merge / --rebase`: Whether to merge remote changes with local changes, or attempt to rebase them on top [default: use default configured for git repo, otherwise merge]

## Sync Behavior

- `--initial-direction DIRECTION`: Initial sync direction (forward = source -> target, reverse = target -> reverse) [default: `forward`, choices: `forward`, `reverse`]
- `--sync-direction DIRECTION`: Sync direction after initialization (forward = source -> target, reverse = target -> reverse) [default: `both`, choices: `both`, `forward`, `reverse`]
- `--conflict MODE`: Conflict resolution mode (only matters for "--sync-direction=both" mode [default: `newer`, choices: `newer`, `source`, `target`, `ask`]
- `--atomic` / `--in-place`: Use atomic file operations to prevent partial writes [default: atomic]
