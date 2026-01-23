# mngr pull - CLI Options Reference

Syncs git state and/or files from one agent (or host) to another agent (or host)

By default, syncs from an agent to somewhere on your local host.

File writes are atomic, but the entire operation is not.

## Usage

```
mngr pull [[--agent] agent] [[--to] other-agent]
```

When two agents are provided, syncs from the first agent to the second agent (instead of to local).

## General

- `--source SOURCE`: Where to pull from. Accepts a unified syntax: `[AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]` [default: agent's work_dir if `--source-agent`, otherwise host root]
- `--source-agent AGENT`: Source agent
- `--source-host HOST`: Source host
- `--source-path PATH`: Source path
- `--target TARGET`: Where to pull to. Accepts a unified syntax: `[AGENT | AGENT.HOST | AGENT.HOST:PATH | HOST:PATH]` [default: local current directory]
- `--target-agent TARGET`: Target agent.
- `--target-host HOST`: Target host.
- `--target-path PATH`: Directory to mount source inside agent host.
- `--stdin`: Read sources (agents and hosts, ids or names) from stdin (one per line)
- `--rsync-arg ARG`: Additional argument to pass to rsync command [repeatable]
- `--rsync-args ARGS`: Additional arguments to pass to rsync command (as a single string)
- `--dry-run`: Show what would be synced without actually syncing

See [multi-target](../generic/multi_target.md) options for behavior when some agents cannot be processed.

## Sync Mode

- `--both`: Sync both git state and files [default]
- `--git-only`: Only sync git state (commits, branches, refs)
- `--files-only`: Only sync file contents (no git operations)

## File Filtering

- `--include-gitignored`: Include files that match `.gitignore` patterns
- `--include PATTERN`: Include files matching glob pattern [repeatable]
- `--exclude PATTERN`: Exclude files matching glob pattern [repeatable]
- `--include-file FILE`: Read include patterns from file (one per line)
- `--exclude-file FILE`: Read exclude patterns from file (one per line)

## Git Options

- `--branch NAME`: Pull a specific branch [repeatable]
- `--target-branch`: Pull a remote branch into a target branch
- `--all, --all-branches`: Pull all remote branches
- `--tags`: Include git tags in sync
- `--force-git`: Force overwrite local git state (use with caution). Allows you to pull even when you have the same branch checked out with local changes.
- `--warn-on-uncommitted-source / --error-on-uncommitted-source`: Warn or error if the source has uncommitted changes and target is not already on the same branch with a clean state [default: error]
- `--merge / --rebase`: Whether to merge remote changes with local changes, or attempt to rebase them on top [default: use default configured for git repo, otherwise merge]

## TODOs

The following features are documented but not yet implemented:

**General Options:**
- `--source-host`, `--target`, `--target-agent`, `--target-host`, `--target-path` (agent-to-agent and remote host operations)
- `--stdin` (reading sources from stdin)
- `--rsync-arg`, `--rsync-args` (custom rsync arguments)

**Sync Mode:**
- `--both`, `--git-only`, `--files-only` (currently only files mode supported, raises NotImplementedError for others)

**File Filtering:**
- `--include-gitignored`, `--include`, `--exclude`, `--include-file`, `--exclude-file` (no filtering support)

**Git Options:**
- All git functionality: `--branch`, `--target-branch`, `--all`/`--all-branches`, `--tags`, `--force-git`, `--warn-on-uncommitted-source`/`--error-on-uncommitted-source`, `--merge`/`--rebase` (no git operations implemented)

**Multi-target:**
- Multi-target operations referenced in documentation not supported
