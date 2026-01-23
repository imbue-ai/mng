# mngr plugin - CLI Options Reference

Manage available and active plugins.

Right now, only `list` is implemented; other commands are placeholders for future functionality.

**Alias:** `plug`

## Usage

```
mngr plugin [ls|list|add|rm|remove|enable|disable] [options]
```

## General

- `--all`: Select all available plugins [default]
- `--active`: Select only currently enabled plugins

## ls, list

- `--format FORMAT`: Output format [default: `human`, choices: `human`, `json`, `jsonl`]. Mutually exclusive with `--json` and `--jsonl` (see [common options](../generic/common.md))
- `--fields FIELDS`: Which fields to include (comma-separated). Available: `name`, `version`, `description`, `enabled`

## TODO

**Note:** The `plugin` command is not yet implemented. The following functionality needs to be added:

- [ ] Create CLI command file (`imbue/mngr/cli/plugin.py`)
- [ ] Implement `ls` / `list` subcommand with `--all`, `--active`, `--format`, and `--fields` options
- [ ] Implement `add` subcommand to install plugins
- [ ] Implement `rm` / `remove` subcommand to uninstall plugins
- [ ] Implement `enable` subcommand to activate plugins
- [ ] Implement `disable` subcommand to deactivate plugins
- [ ] Add plugin status tracking (enabled/disabled state)
- [ ] Register command in `main.py` BUILTIN_COMMANDS list
