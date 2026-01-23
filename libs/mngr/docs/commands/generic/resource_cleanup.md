## Resource Cleanup

- `--keep-nothing`: Do not preserve any resources when destroying agents (default behavior)
- `--keep-containers`: Preserve Docker/Modal containers/sandboxes/local folders when destroying agents
- `--keep-snapshots`: Preserve snapshots when destroying agents
- `--keep-images`: Preserve Docker/Modal images when destroying agents
- `--keep-volumes`: Preserve Docker/Modal volumes when destroying agents
- `--keep-logs`: Preserve log files when destroying agents
- `--keep-cache`: Preserve build cache when destroying agents
- `--keep-clones`: Preserve git clones when destroying agents

## TODO

All documented `--keep-*` flags are not yet implemented. Current cleanup uses `mngr gc` command instead. Missing features:

- `--keep-nothing` flag on destroy command
- `--keep-containers` flag (container-level tracking not implemented)
- `--keep-snapshots` flag (snapshots cleaned via gc, not selective on destroy)
- `--keep-images` flag (image cleanup not implemented)
- `--keep-volumes` flag (volumes cleaned via gc, not selective on destroy)
- `--keep-logs` flag (logs cleaned via gc, not selective on destroy)
- `--keep-cache` flag (cache cleaned via gc, not selective on destroy)
- `--keep-clones` flag (work dirs cleaned via gc, not selective on destroy)
