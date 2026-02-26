The allowed import order for the modules in this directory is as follows (from highest level to lowest level).

This matches the import-linter contract in the root pyproject.toml:

- `main`
- `cli`
- `deploy`
- `server`
- `config`
- `mng_commands`
- `data_types`
- `errors`
- `primitives`

Lower-level modules may not import from higher-level modules, but higher-level modules may import from lower-level modules.
This is to ensure a clear separation of concerns and to avoid circular dependencies.

Additional modules that are not yet in the import-linter contract (and may be added as the project grows):

- `desktop_client` (above cli)
- `deployment` (near deploy)
- `core` (below server)
- `interfaces` (below core)
- `utils` (below errors)
