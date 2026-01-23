# mngr migrate - CLI Options Reference

Migrate an agent from one host to another.

Basically just an alias for `mngr clone` followed by `mngr destroy`

## TODOs

The following functionality is not yet implemented:

- `mngr migrate` command itself (no command registered in main.py)
- `mngr clone` command (dependency - should be an alias for `mngr create --from-agent`)

Note: The underlying functionality exists (`mngr create --from-agent` and `mngr destroy` are both implemented)
