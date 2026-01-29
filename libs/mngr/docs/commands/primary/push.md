# mngr push - CLI Options Reference

Pushes files or git commits from a local directory to an agent's working directory.

By default, syncs from your local machine to an agent using rsync for efficient incremental file transfer.

This is the equivalent of a "manual sync" operation, pushing your local changes to the remote agent host.

File writes are atomic, but the entire operation is not.

## Usage

```
mngr push [TARGET] [SOURCE]
```

Where TARGET can be:
- `AGENT` - Push to agent's work_dir
- `AGENT:PATH` - Push to specific path within agent's work_dir

## Target Selection

- `--target TARGET`: Target specification (AGENT or AGENT:PATH)
- `--target-agent AGENT`: Target agent name or ID
- `--target-host HOST`: Target host name or ID (for remote agents)
- `--target-path PATH`: Path within the agent's work directory

## Source

- `--source PATH`: Local source directory [default: current directory]

## Sync Options

- `--dry-run`: Show what would be transferred without actually transferring
- `--stop`: Stop the agent after pushing (for state consistency)
- `--delete / --no-delete`: Delete files in destination that don't exist in source
- `--sync-mode MODE`: What to sync: `files` (working directory via rsync), `git` (merge git branches), or `full` (everything) [default: files]
- `--exclude PATTERN`: Patterns to exclude from sync [repeatable]

## Git Options (when --sync-mode=git)

- `--source-branch NAME`: Branch to push from [default: current branch]
- `--mirror / --no-mirror`: Use git push --mirror (dangerous - replaces all refs in agent repo)

## Uncommitted Changes Handling

- `--uncommitted-changes MODE`: How to handle uncommitted changes in the agent workspace:
  - `fail`: Error if uncommitted changes exist [default]
  - `stash`: Stash changes before pushing (leaves changes stashed)
  - `merge`: Stash, push, then unstash (attempts to preserve local changes)
  - `clobber`: Overwrite uncommitted changes

## Examples

```bash
# Push current directory to agent's work_dir
mngr push my-agent

# Push specific directory to agent
mngr push my-agent ./local-copy

# Push to specific path in agent's work_dir
mngr push my-agent:src ./local-src

# Push using explicit options
mngr push --target-agent my-agent --source ./local-copy

# Push git commits instead of files
mngr push my-agent --sync-mode=git

# Push from specific branch
mngr push my-agent --sync-mode=git --source-branch=feature

# Push and stop agent for consistency
mngr push my-agent --stop

# Stash agent's uncommitted changes before pushing
mngr push my-agent --uncommitted-changes=stash
```
