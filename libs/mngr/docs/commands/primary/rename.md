# mngr rename - CLI Options Reference

Rename an agent or host.

If an in-progress rename failed, will attempt to finish it.

## Usage

```
mngr rename <current> <new-name>
```

## Arguments

- `current`: Current name or ID of the agent/host to rename
- `new-name`: New name for the agent/host

## Options

- `--dry-run`: Show what would be renamed without actually renaming

## TODOs

The following features are not yet implemented:

- [ ] CLI command wrapper (no `cli/rename.py` exists yet)
- [ ] Agent renaming support (only host renaming exists at provider level)
- [ ] `--dry-run` flag implementation
- [ ] Resume/recovery logic for failed rename operations
- [ ] Integration with locking system per spec requirements
