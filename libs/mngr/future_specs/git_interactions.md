# Git Interactions Spec

How mngr handles git state during sync operations.

## Definitions

- **"git state"**: Everything in the `.git` directory, except hooks and config (which are ignored or not depending on config vars)
- **"files"**: Everything outside the `.git` directory (the working tree)

## Sync Modes

- `--sync-mode state`: Only sync git state (refs, objects, etc.), not working tree files
- `--sync-mode files`: Only sync working tree files, explicitly excluding `.git` directory contents (default, only mode currently implemented)
- `--sync-mode full`: Sync both state and files

Syncing files-only can cause git to see the working tree as "dirty" (this is expected behavior).

## Conflict Handling

### Push/Pull

When local and remote have diverged [future]:
- `--merge`: Attempts a merge; if it fails, the command fails and user resolves manually
- `--rebase`: Attempts a rebase; if it fails, the command fails and user resolves manually

If uncommitted changes exist and the underlying git command fails, mngr fails too. Standard git behavior applies.

If remote has force-pushed and history diverged, the command fails. User must fix manually.

### Pair Mode [future]

Conflicts are handled differently depending on when they occur:

**During initial sync:**
- Abort immediately if conflicts exist

**During ongoing sync:**
- Governed by `--conflict MODE`:
  - `newer`: Use whichever version the sync process learned about most recently (clock skew doesn't matter)
  - `local`: Always prefer local version
  - `remote`: Always prefer remote version
  - `ask`: Prompt the user to resolve

## Submodules

Submodules are **not supported**. Recursive `.git` directories are ignored entirely.

## Partial Writes

During rapid concurrent edits in pair mode, changes are debounced to avoid partial writes. [future]
