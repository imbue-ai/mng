# Pair Command Spec

Implementation details for the `mngr pair` command.

## Conflict Resolution

### "Newer" Mode

"Newer" means "newer according to when the sync process learned about it"—not file modification time. This avoids clock skew issues between hosts.

### Partial Writes

Rapid concurrent edits are debounced. The sync process waits for writes to settle before syncing to avoid capturing partial file states.

## Git Commit Handling

When using pair mode with git:

- A commit on one side is transferred to the other side
- If a branch change occurs on either side:
  - Option to abort pairing
  - Option to track the new branch and continue
- Rapidly making git changes on both sides can create screwy states, but conflict resolution will eventually settle to one side

## Branch Tracking

The `--track-branch-changes` option controls behavior when the branch changes:
- `abort`: Stop pairing if branch changes
- `follow`: Switch to tracking the new branch
