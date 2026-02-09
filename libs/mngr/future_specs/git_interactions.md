# Git Interactions Spec

How mngr handles git state during sync operations.

## Definitions

- **"git state"**: Everything in the `.git` directory, except hooks and config (which are ignored or not depending on config vars)
- **"files"**: Everything outside the `.git` directory (the working tree)

## Sync Modes

- `--sync-mode files`: Only sync working tree files, explicitly excluding `.git` directory contents (default)
- `--sync-mode git`: Sync git state (branches, commits) via fetch
- `--sync-mode state` [future]: Only sync git state (refs, objects, etc.), not working tree files
- `--sync-mode full` [future]: Sync both state and files

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

## Transport Mechanism

Push and pull both use `git fetch` to transfer objects between repositories:

- **Push (local agents)**: The target repo fetches from the source, then does `git reset --hard FETCH_HEAD` to update the working tree. This avoids `receive.denyCurrentBranch` errors that occur with `git push` when the target branch is checked out (which is always the case for local worktrees).
- **Pull**: The local repo fetches from the agent, then merges `FETCH_HEAD` into the target branch.
- **Push (remote agents)** [future]: Will likely use `git push` over SSH, where the checked-out branch problem can be handled server-side.

### Mirror mode (`--mirror`)

For local agents, `--mirror` fetches all refs (`refs/*:refs/*`) with `--force` and `--update-head-ok`, then resets the working tree. This overwrites all branches and tags in the target to match the source. Remote agent mirror support is not yet implemented [future]; it will likely use `git push --mirror`.

## Submodules

Submodules are **not supported**. Recursive `.git` directories are ignored entirely.

## Partial Writes

During rapid concurrent edits in pair mode, changes are debounced to avoid partial writes. [future]
