# mngr clone - CLI Options Reference

Create a new agent by cloning an existing one.

Basically just an alias for `mngr create --from-agent <agent>`

## TODOs

- **Clone command alias**: The `mngr clone` command is not registered in main.py. Need to add `cli.add_command(create, name="clone")` with appropriate parameter mapping.
- **Snapshot functionality**: The `_snapshot_source_agent()` function in create.py:1029 is stubbed and raises NotImplementedError. This is needed for proper remote agent cloning with the `--snapshot-source` flag.
