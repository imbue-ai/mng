# mngr rename - CLI Options Reference

Rename an agent.

If an in-progress rename failed, will attempt to finish it.

## Usage

```
mngr rename <current> <new-name>
```

## Arguments

- `current`: Current name or ID of the agent to rename
- `new-name`: New name for the agent

## Options

- `--dry-run`: Show what would be renamed without actually renaming

## Examples

Rename an agent:

```
mngr rename my-agent new-name
```

Preview what would be renamed:

```
mngr rename my-agent new-name --dry-run
```

Use the alias:

```
mngr mv my-agent new-name
```

## Notes

- Git branch names are not renamed. You may want to rename them manually.
- The tmux session is renamed if the agent is currently running.
- If a previous rename was interrupted (e.g., data.json was updated but the tmux session was not renamed), re-running the command will attempt to complete it.
