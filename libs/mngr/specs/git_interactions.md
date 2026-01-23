# Git Interactions Spec

How mngr handles git state during sync operations.

## Definitions

- **"git state"**: Everything in the `.git` directory, except hooks and config (which are ignored or not depending on config vars)
- **"files"**: Everything outside the `.git` directory (the working tree)

## Sync Modes

- `--git-only`: Only sync git state (refs, objects, etc.), not working tree files
- `--files-only`: Only sync working tree files, explicitly excluding `.git` directory contents

Syncing files-only can cause git to see the working tree as "dirty" (this is expected behavior).

## Conflict Handling

### Push/Pull

When local and remote have diverged:
- `--merge`: Attempts a merge; if it fails, the command fails and user resolves manually
- `--rebase`: Attempts a rebase; if it fails, the command fails and user resolves manually

If uncommitted changes exist and the underlying git command fails, mngr fails too. Standard git behavior applies.

If remote has force-pushed and history diverged, the command fails. User must fix manually.

### Pair Mode

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

During rapid concurrent edits in pair mode, changes are debounced to avoid partial writes.

## TODOs

Features not yet implemented:

- `--git-only` and `--files-only` sync modes (only files mode currently works)
- `--merge` and `--rebase` options for push/pull conflict resolution
- Pair mode with `--conflict` options (newer, local, remote, ask)
- Debouncing for rapid concurrent edits in pair mode
